from contextlib import contextmanager
import logging

from collections import OrderedDict

from kinto.core.events import ACTIONS
from kinto.core.storage import Filter, Sort
from kinto.core.storage.exceptions import UnicityError, RecordNotFoundError
from kinto.core.utils import COMPARISON, build_request

from kinto_signer.serializer import canonical_json
from kinto_signer.utils import STATUS

logger = logging.getLogger(__name__)


FIELD_ID = 'id'
FIELD_LAST_MODIFIED = 'last_modified'
FIELD_LAST_AUTHOR = 'last_author'
FIELD_LAST_EDITOR = 'last_editor'
FIELD_LAST_REVIEWER = 'last_reviewer'


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
                                      timestamp=record[FIELD_LAST_MODIFIED],
                                      data=record,
                                      action=action,
                                      old=old)


def _ensure_resource(resource):
    if not set(resource.keys()).issuperset({'bucket', 'collection'}):
        msg = "Resources should contain both bucket and collection"
        raise ValueError(msg)
    return resource


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
        self._source = None
        self._destination = None

        self.source = source
        self.destination = destination
        self.signer = signer
        self.storage = storage
        self.permission = permission

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, source):
        self._source = _ensure_resource(source)
        self.source_bucket_uri = '/buckets/%s' % source['bucket']
        self.source_collection_uri = '/buckets/%s/collections/%s' % (
            source['bucket'],
            source['collection'])

    @property
    def destination(self):
        return self._destination

    @destination.setter
    def destination(self, destination):
        self._destination = _ensure_resource(destination)
        self.destination_bucket_uri = '/buckets/%s' % (
            self.destination['bucket'])
        self.destination_collection_uri = '/buckets/%s/collections/%s' % (
            self.destination['bucket'],
            self.destination['collection'])

    def sign_and_update_destination(self, request, source,
                                    next_source_status=STATUS.SIGNED):
        """Sign the specified collection.

        0. Create the destination bucket / collection
        1. Get all the records of the collection
        2. Send all records since the last_modified of the destination
        3. Compute a hash of these records
        4. Ask the signer for a signature
        5. Send the signature to the destination.
        """
        with self.send_events(request):
            self.create_destination(request)

            self.push_records_to_destination(request)

            records, timestamp = self.get_destination_records()
            serialized_records = canonical_json(records, timestamp)
            logger.debug(self.source_collection_uri + ":\t" + serialized_records)
            signature = self.signer.sign(serialized_records)

            self.set_destination_signature(signature, source, request)
            self.update_source_status(next_source_status, request)
            self.invalidate_cloudfront_cache(request, timestamp)

    @contextmanager
    def send_events(self, request):
        # Backup resource events generated until now and set it to empty dict.
        before_events = request.bound_data["resource_events"]
        request.bound_data["resource_events"] = OrderedDict()
        yield
        # The resource events we gathered during listeners and hooks of kinto-signer
        # can now be added to ``kinto_signer.events`` which will be sent later
        # in ``listeners.send_signer_events()``.
        new_events = request.get_resource_events()
        request.bound_data.setdefault('kinto_signer.events', []).extend(new_events)
        # Restore backup.
        request.bound_data["resource_events"] = before_events

    def _ensure_resource_exists(self, resource_type, parent_id,
                                record_id, request, **attributes):
        attributes.update({FIELD_ID: record_id})
        try:
            created = self.storage.create(
                collection_id=resource_type,
                parent_id=parent_id,
                record=attributes)
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
                                  matchdict={FIELD_ID: self.destination['bucket']},
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
                                      FIELD_ID: self.destination['collection']
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

    def _get_records(self, rc, last_modified=None):
        # If last_modified was specified, only retrieve items since then.
        storage_kwargs = {}
        if last_modified is not None:
            gt_last_modified = Filter(FIELD_LAST_MODIFIED, last_modified,
                                      COMPARISON.GT)
            storage_kwargs['filters'] = [gt_last_modified, ]

        storage_kwargs['sorting'] = [Sort(FIELD_LAST_MODIFIED, 1)]
        parent_id = "/buckets/{bucket}/collections/{collection}".format(**rc)

        records, count = self.storage.get_all(
            parent_id=parent_id,
            collection_id='record',
            include_deleted=True,
            **storage_kwargs)

        if len(records) == count == 0:
            # When the collection empty (no records and no tombstones)
            collection_timestamp = None
        else:
            collection_timestamp = self.storage.collection_timestamp(
                parent_id=parent_id,
                collection_id='record')

        return records, collection_timestamp

    def get_source_records(self, last_modified):
        return self._get_records(self.source,
                                 last_modified)

    def get_destination_records(self):
        return self._get_records(self.destination)

    def push_records_to_destination(self, request):
        __, dest_timestamp = self.get_destination_records()
        new_records, source_timestamp = self.get_source_records(last_modified=dest_timestamp)

        if source_timestamp and dest_timestamp and dest_timestamp > source_timestamp:
            raise ValueError("Destination collection timestamp cannot be higher "
                             "than source collection timestamp. Check that your "
                             "storage backend timezone is UTC.")

        # Update the destination collection.
        for record in new_records:
            storage_kwargs = {
                "parent_id": self.destination_collection_uri,
                "collection_id": 'record',
            }
            try:
                before = self.storage.get(object_id=record[FIELD_ID],
                                          **storage_kwargs)
            except RecordNotFoundError:
                before = None

            deleted = record.get('deleted', False)
            if deleted:
                try:
                    pushed = self.storage.delete(
                        object_id=record[FIELD_ID],
                        last_modified=record[FIELD_LAST_MODIFIED],
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
                        object_id=record[FIELD_ID],
                        record=record,
                        **storage_kwargs)
                    action = ACTIONS.UPDATE

            matchdict = {
                'bucket_id': self.destination['bucket'],
                'collection_id': self.destination['collection'],
                FIELD_ID: record[FIELD_ID]
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

    def set_destination_signature(self, signature, source_attributes, request):
        # Push the new signature to the destination collection.
        parent_id = '/buckets/%s' % self.destination['bucket']
        collection_id = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.destination['collection'])

        # Update the collection_record
        new_collection = dict(**collection_record)
        new_collection.pop(FIELD_LAST_MODIFIED, None)
        new_collection['signature'] = signature
        # Copy some Kinto-Admin UI attributes from source to destination.
        for attr in ('sort', 'displayFields', 'attachment'):
            if attr in source_attributes:
                new_collection.setdefault(attr, source_attributes[attr])

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

    def update_source_editor(self, request):
        attrs = {FIELD_LAST_EDITOR: request.prefixed_userid}
        return self._update_source_attributes(request, **attrs)

    def update_source_status(self, status, request):
        attrs = {'status': status.value}
        if status == STATUS.WORK_IN_PROGRESS:
            attrs[FIELD_LAST_AUTHOR] = request.prefixed_userid
        if status == STATUS.TO_REVIEW:
            attrs[FIELD_LAST_EDITOR] = request.prefixed_userid
        if status == STATUS.SIGNED:
            attrs[FIELD_LAST_REVIEWER] = request.prefixed_userid
        return self._update_source_attributes(request, **attrs)

    def _update_source_attributes(self, request, **kwargs):
        parent_id = '/buckets/%s' % self.source['bucket']
        collection_id = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.source['collection'])

        # Update the collection_record
        new_collection = dict(**collection_record)
        new_collection.update(**kwargs)

        # If nothing was changed, do nothing.
        # (e.g. same last_editor)
        if new_collection == collection_record:
            return

        # Remove last_modified to be sure it's bumped.
        new_collection.pop('last_modified', None)

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

    def invalidate_cloudfront_cache(self, request, timestamp):
        collection_paths = "/v1/%s*" % self.destination_collection_uri
        distribution_id = request.registry.settings.get('signer.distribution_id')

        if distribution_id:
            # Create a boto client
            import boto3
            client = boto3.client('cloudfront')

            # Invalidate
            client.create_invalidation(
                DistributionId=distribution_id,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': 1,
                        'Items': [
                            collection_paths
                        ]
                    },
                    'CallerReference': str(timestamp)
                })
