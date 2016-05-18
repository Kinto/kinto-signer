from kinto.core.utils import COMPARISON
from kinto_signer.serializer import canonical_json
from kinto.core.storage import Filter
from kinto.core.storage.exceptions import UnicityError, RecordNotFoundError


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

        self.destination_bucket_id = '/buckets/%s' % self.destination['bucket']
        self.destination_collection_id = '/buckets/%s/collections/%s' % (
            self.destination['bucket'],
            self.destination['collection'])

        self.source_bucket_id = '/buckets/%s' % self.source['bucket']
        self.source_collection_id = '/buckets/%s/collections/%s' % (
            self.source['bucket'],
            self.source['collection'])

    def sign_and_update_destination(self):
        """Sign the specified collection.

        0. Create the destination bucket / collection
        1. Get all the records of the collection
        2. Compute a hash of these records
        3. Ask the signer for a signature
        4. Send all records since the last_modified field of the Authoritative
           server
        5. Send the signature to the Authoritative server.
        """
        self.create_destination()
        records = self.get_source_records()
        serialized_records = canonical_json(records)
        signature = self.signer.sign(serialized_records)

        self.push_records_to_destination()
        self.set_destination_signature(signature)
        self.update_source_status("signed")

    def _ensure_resource_exists(self, resource_type, parent_id, record_id):
        try:
            self.storage.create(
                collection_id=resource_type,
                parent_id=parent_id,
                record={'id': record_id})
        except UnicityError:
            pass

    def create_destination(self):
        # Create the destination bucket/collection if they don't already exist.
        bucket_name = self.destination['bucket']
        collection_name = self.destination['collection']

        self._ensure_resource_exists('bucket', '', bucket_name)
        self._ensure_resource_exists(
            'collection',
            self.destination_bucket_id,
            collection_name)

        # Set the permissions on the destination collection.
        # With the current implementation, the destination is not writable by
        # anyone and readable by everyone.
        # https://github.com/Kinto/kinto-signer/issues/55
        permissions = {'read': ("system.Everyone",)}
        self.permission.replace_object_permissions(
            self.destination_collection_id, permissions)

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
        return records

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

    def push_records_to_destination(self):
        last_modified, records_count = self.get_destination_last_modified()
        if records_count == 0:
            last_modified = None
        new_records = self.get_source_records(
            last_modified,
            include_deleted=True)

        # Update the destination collection.
        for record in new_records:
            if record.get('deleted', False):
                try:
                    self.storage.delete(
                        parent_id=self.destination_collection_id,
                        collection_id='record',
                        object_id=record['id'],
                    )
                except RecordNotFoundError:
                    # If the record doesn't exists in the destination
                    # we are good and can ignore it.
                    pass
            else:
                self.storage.update(
                    parent_id=self.destination_collection_id,
                    collection_id='record',
                    object_id=record['id'],
                    record=record)

    def set_destination_signature(self, signature):
        # Push the new signature to the destination collection.
        parent_id = '/buckets/%s' % self.destination['bucket']
        collection_id = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.destination['collection'])

        collection_record['signature'] = signature

        self.storage.update(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.destination['collection'],
            record=collection_record)

    def update_source_status(self, status):
        parent_id = '/buckets/%s' % self.source['bucket']
        collection_id = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.source['collection'])

        collection_record['status'] = status

        self.storage.update(
            parent_id=parent_id,
            collection_id=collection_id,
            object_id=self.source['collection'],
            record=collection_record)
