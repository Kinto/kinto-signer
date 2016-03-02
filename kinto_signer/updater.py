from cliquet.utils import COMPARISON
from kinto_signer.serializer import canonical_json
from cliquet.storage import Filter


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
        The instance of cliquet.storage that will be used to retrieve records
        from the source and add new items to the destination.
    """

    def __init__(self, source, destination, signer, storage):

        def _ensure_bucket_and_collection(resource):
            if not set(resource.keys()).issuperset({'bucket', 'collection'}):
                msg = "Resources should contain both bucket and collection"
                raise ValueError(msg)

        self.source = source
        self.destination = destination
        self.signer = signer
        self.storage = storage

    def sign_and_update_remote(self):
        """Sign the specified collection.

        1. Get all the records of the collection;
        2. Compute a hash of these records;
        3. Ask the signer for a signature;
        4. Send all records since the last_modified field of the Authoritative
           server;
        5. Send the signature to the Authoritative server.
        """
        records = self.get_local_records()
        serialized_records = canonical_json(records)
        signature = self.signer.sign(serialized_records)

        # XXX Handle creation of the destination?
        # XXX Handle permissions on the destination.
        self.push_records_to_destination()
        self.set_destination_signature(signature)

    def get_local_records(self, last_modified=None):
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
            collection_id='record', **storage_kwargs)
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
        new_records = self.get_local_records(last_modified)

        # Update the destination collection.
        parent_id = "/buckets/%s/collections/%s" % (
            self.destination['bucket'], self.destination['collection'])
        for record in new_records:
            self.storage.update(
                parent_id=parent_id,
                collection_id='record',
                object_id=record['id'],
                record=record)

        # XXX delete records as well.

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
