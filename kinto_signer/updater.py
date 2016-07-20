from pyramid import httpexceptions

from kinto.core.utils import COMPARISON, build_request, instance_uri
from kinto_signer.serializer import canonical_json
from kinto.core.storage import Filter


def _invoke_subrequest(request, params):
    subrequest = build_request(request, params)
    subrequest.bound_data = request.bound_data  # Contains resource events.
    return request.invoke_subrequest(subrequest)


def _ensure_resource_exists(request, uri):
    try:
        _invoke_subrequest(request, {
            'method': 'PUT',
            'path': uri,
            'headers': {'If-None-Match': '*'}
        })
    except httpexceptions.HTTPPreconditionFailed:
        pass


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

    def create_destination(self, request):
        # Create the destination bucket/collection if they don't already exist.
        bucket_uri = instance_uri(request,
                                  'bucket',
                                  id=self.destination['bucket'])
        _ensure_resource_exists(request, bucket_uri)

        collection_uri = instance_uri(request,
                                      'collection',
                                      bucket_id=self.destination['bucket'],
                                      id=self.destination['collection'])
        _ensure_resource_exists(request, collection_uri)

        # Set the permissions on the destination collection.
        # With the current implementation, the destination is not writable by
        # anyone and readable by everyone.
        # https://github.com/Kinto/kinto-signer/issues/55
        permissions = {'read': ("system.Everyone",)}
        self.permission.replace_object_permissions(collection_uri, permissions)

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
            uri = instance_uri(request, 'record',
                               bucket_id=self.destination['bucket'],
                               collection_id=self.destination['collection'],
                               id=record['id'])

            if record.get('deleted', False):
                uri += "?last_modified=%s" % record['last_modified']
                try:
                    _invoke_subrequest(request, {
                        'method': 'DELETE',
                        'path': uri
                    })
                except httpexceptions.HTTPNotFound:
                    # If the record doesn't exists in the destination
                    # we are good and can ignore it.
                    pass
            else:
                _invoke_subrequest(request, {
                    'method': 'PUT',
                    'path': uri,
                    'body': {'data': record}
                })

    def set_destination_signature(self, signature, request):
        # Push the new signature to the destination collection.
        uri = instance_uri(request, 'collection',
                           bucket_id=self.destination['bucket'],
                           id=self.destination['collection'])
        _invoke_subrequest(request, {
            'method': 'PATCH',
            'path': uri,
            'body': {'data': {'signature': signature}}
        })

    def update_source_status(self, status, request):
        uri = instance_uri(request, 'collection',
                           bucket_id=self.source['bucket'],
                           id=self.source['collection'])
        _invoke_subrequest(request, {
            'method': 'PATCH',
            'path': uri,
            'body': {'data': {'status': 'signed'}}
        })
