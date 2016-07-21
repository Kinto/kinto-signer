from kinto.core.events import ACTIONS
from kinto.core.storage import Filter
from kinto.core.storage.exceptions import UnicityError, RecordNotFoundError
from kinto.core.utils import COMPARISON, build_request
from kinto_signer.serializer import canonical_json


def notify_resource_event(request, request_options, matchdict,
                          resource_name, parent_id, record, action, old=None):
    """Private helper that triggers resource events when the updater modifies
    the source and destination objects.
    """
    fakerequest = build_request(request, request_options)
    fakerequest.matchdict = matchdict
    fakerequest.bound_data = request.bound_data
    fakerequest.selected_userid = "kinto-signer"
    fakerequest.authn_type = "plugin"
    fakerequest.current_resource_name = resource_name
    fakerequest.notify_resource_event(parent_id=parent_id,
                                      timestamp=record['last_modified'],
                                      data=record,
                                      action=action,
                                      old=old)


class LocalUpdater(object):
    """Sign items in the source and push them to the destination.

    Triggers a signature of all records in the source destination, and
    eventually update the destination with the new signature and the updated
    records.

    :param source:
        Python dictionary containing the bucket and collection of the source.

    :param destination:
        Python dictionary containing the bucket and collection of the
        destination.

    :param signer:
        The instance of the signer that will be used to generate the signature
        on the collection.

    :param storage:
        The instance of kinto.core.storage that will be used to retrieve
        records from the source and add new items to the destination.
    """

    def __init__(self, source, destination, signer, storage, permission):

        def _ensure_resource(resource):
            if not set(resource.keys()).issuperset({'bucket', 'collection'}):
                msg = "Resources should contain both bucket and collection"
                raise ValueError(msg)
            return resource

        self.source = _ensure_resource(source)
        self.destination = _ensure_resource(destination)
        self.signer = signer
        self.storage = storage
        self.permission = permission

        # Define resource IDs.

        self.destination_bucket_uri = '/buckets/%s' % (
            self.destination['bucket'])
        self.destination_collection_uri = '/buckets/%s/collections/%s' % (
            self.destination['bucket'],
            self.destination['collection'])

        self.source_bucket_uri = '/buckets/%s' % self.source['bucket']
        self.source_collection_uri = '/buckets/%s/collections/%s' % (
            self.source['bucket'],
            self.source['collection'])

    def sign_and_update_destination(self, request):
        """Sign the specified collection.

        0. Create the destination bucket / collection
        1. Get all the records of the collection
        2. Compute a hash of these records
        3. Ask the signer for a signature
        4. Send all records since the last_modified field of the Authoritative
           server
        5. Send the signature to the Authoritative server.
        """
        before = len(request.get_resource_events())

        self.create_destination(request)
        records, last_modified = self.get_source_records()
        serialized_records = canonical_json(records, last_modified)
        signature = self.signer.sign(serialized_records)

        self.push_records_to_destination(request)
        self.set_destination_signature(signature, request)
        self.update_source_status("signed", request)

        # Re-trigger events from event listener \o/
        for event in request.get_resource_events()[before:]:
            request.registry.notify(event)

    def _ensure_resource_exists(self, resource_type, parent_id,
                                record_id, request):
        try:
            created = self.storage.create(
                collection_id=resource_type,
                parent_id=parent_id,
                record={'id': record_id})
        except UnicityError:
            created = None
        return created

    def create_destination(self, request):
        # Create the destination bucket/collection if they don't already exist.
        bucket_name = self.destination['bucket']
        collection_name = self.destination['collection']

        created = self._ensure_resource_exists('bucket', '',
                                               bucket_name,
                                               request)
        if created:
            notify_resource_event(request,
                                  {'method': 'PUT',
                                   'path': self.destination_bucket_uri},
                                  matchdict={'id': self.destination['bucket']},
                                  resource_name="bucket",
                                  parent_id='',
                                  record=created,
                                  action=ACTIONS.CREATE)

        created = self._ensure_resource_exists(
            'collection',
            self.destination_bucket_uri,
            collection_name,
            request)
        if created:
            notify_resource_event(request,
                                  {'method': 'PUT',
                                   'path': self.destination_collection_uri},
                                  matchdict={
                                      'bucket_id': self.destination['bucket'],
                                      'id': self.destination['collection']
                                  },
                                  resource_name="collection",
                                  parent_id=self.destination_bucket_uri,
                                  record=created,
                                  action=ACTIONS.CREATE)

        # Set the permissions on the destination collection.
        # With the current implementation, the destination is not writable by
        # anyone and readable by everyone.
        # https://github.com/Kinto/kinto-signer/issues/55
        permissions = {'read': ("system.Everyone",)}
        self.permission.replace_object_permissions(
            self.destination_collection_uri, permissions)

    def get_source_records(self, last_modified=None, include_deleted=False):
        # If last_modified was specified, only retrieve items since then.
        storage_kwargs = {}
        if last_modified is not None:
            gt_last_modified = Filter('last_modified', last_modified,
                                      COMPARISON.GT)
            storage_kwargs['filters'] = [gt_last_modified, ]

        parent_id = "/buckets/%s/collections/%s" % (
            self.source['bucket'], self.source['collection'])

        records, _ = self.storage.get_all(
            parent_id=parent_id,
            collection_id='record',
            include_deleted=include_deleted,
            **storage_kwargs)
        timestamp = self.storage.collection_timestamp(
            parent_id=parent_id,
            collection_id='record')
        return records, timestamp

    def get_destination_last_modified(self):
        parent_id = "/buckets/%s/collections/%s" % (
            self.destination['bucket'], self.destination['collection'])

        collection_timestamp = self.storage.collection_timestamp(
            parent_id=parent_id,
            collection_id='record')

        _, records_count = self.storage.get_all(
            parent_id=parent_id,
            collection_id='record')

        return collection_timestamp, records_count

    def push_records_to_destination(self, request):
        last_modified, records_count = self.get_destination_last_modified()
        if records_count == 0:
            last_modified = None
        new_records, _ = self.get_source_records(
            last_modified,
            include_deleted=True)

        # Update the destination collection.
        for record in new_records:
            storage_kwargs = {
                "parent_id": self.destination_collection_uri,
                "collection_id": 'record',
            }
            try:
                before = self.storage.get(object_id=record['id'],
                                          **storage_kwargs)
            except RecordNotFoundError:
                before = None

            deleted = record.get('deleted', False)
            if deleted:
                try:
                    pushed = self.storage.delete(
                        object_id=record['id'],
                        last_modified=record['last_modified'],
                        **storage_kwargs
                    )
                    action = ACTIONS.DELETE
                except RecordNotFoundError:
                    # If the record doesn't exists in the destination
                    # we are good and can ignore it.
                    continue
            else:
                if before is None:
                    pushed = self.storage.create(
                        record=record,
                        **storage_kwargs)
                    action = ACTIONS.CREATE
                else:
                    pushed = self.storage.update(
                        object_id=record['id'],
                        record=record,
                        **storage_kwargs)
                    action = ACTIONS.UPDATE

            matchdict = {
                'bucket_id': self.destination['bucket'],
                'collection_id': self.destination['collection'],
                'id': record['id']
            }
            record_uri = ('/buckets/{bucket_id}'
                          '/collections/{collection_id}'
                          '/records/{id}'.format(**matchdict))
            notify_resource_event(
                request,
                {'method': 'DELETE' if deleted else 'PUT',
                 'path': record_uri},
                matchdict=matchdict,
                resource_name="record",
                parent_id=self.destination_collection_uri,
                record=pushed,
                action=action,
                old=before)

    def set_destination_signature(self, signature, request):
        # Push the new signature to the destination collection.
        parent_id = '/buckets/%s' % self.destination['bucket']
        collection_id = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.destination['collection'])

        # Update the collection_record
        new_collection = dict(**collection_record)
        new_collection.pop('last_modified', None)
        new_collection['signature'] = signature

        updated = self.storage.update(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.destination['collection'],
            record=new_collection)

        matchdict = dict(bucket_id=self.destination['bucket'],
                         id=self.destination['collection'])
        notify_resource_event(
            request,
            {
                'method': 'PUT',
                'path': self.destination_collection_uri
            },
            matchdict=matchdict,
            resource_name="collection",
            parent_id=self.destination_bucket_uri,
            record=updated,
            action=ACTIONS.UPDATE,
            old=collection_record)

    def update_source_status(self, status, request):
        parent_id = '/buckets/%s' % self.source['bucket']
        collection_id = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.source['collection'])

        # Update the collection_record
        new_collection = dict(**collection_record)
        new_collection.pop('last_modified', None)
        new_collection['status'] = status

        updated = self.storage.update(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.source['collection'],
            record=new_collection)

        matchdict = dict(bucket_id=self.source['bucket'],
                         id=self.source['collection'])
        notify_resource_event(
            request,
            {
                'method': 'PUT',
                'path': self.source_collection_uri
            },
            matchdict=matchdict,
            resource_name="collection",
            parent_id=self.source_bucket_uri,
            record=updated,
            action=ACTIONS.UPDATE,
            old=collection_record)
