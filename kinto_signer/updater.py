from cliquet.utils import COMPARISON
from kinto_signer import hasher
from cliquet.storage import Filter


class RemoteUpdater(object):

    def __init__(self, remote, signer, storage, bucket_id, collection_id):
        self.remote = remote
        self.signer = signer
        self.storage = storage
        self.bucket_id = bucket_id
        self.collection_id = collection_id

    def sign_and_update_remote(self):
        """Sign the specified collection.

        1. Get all the records of the collection;
        2. Compute a hash of these records;
        3. Ask the signer for a signature;
        4. Send all records since the last_modified field of the Authoritative
           server;
        5. Send the signature to the Authoritative server.
        """
        records = self.get_collection_records()
        new_hash = hasher.compute_hash(records)
        signature = self.signer.sign(new_hash)
        self.update_remote(new_hash, signature)

    def get_collection_records(self, last_modified=None):
        # If a last_modified value was specified, filter on it.
        storage_kwargs = {}
        if last_modified is not None:
            gt_last_modified = Filter('last_modified', last_modified,
                                      COMPARISON.GT)
            storage_kwargs['filters'] = [gt_last_modified, ]

        parent_id = "/buckets/%s/collections/%s" % (
            self.bucket_id, self.collection_id)

        records, _ = self.storage.get_all(
            parent_id=parent_id,
            collection_id='record', **storage_kwargs)
        return records

    def get_remote_last_modified(self):
        endpoint = self.remote._get_endpoint('records')
        # XXX Replace with a HEAD request.

        _, headers = self.remote.session.request('get', endpoint)
        collection_timestamp = int(headers['ETag'].strip('"'))
        records_count = int(headers['Total-Records'])

        return collection_timestamp, records_count

    def update_remote(self, new_hash, signature):
        last_modified, records_count = self.get_remote_last_modified()
        if records_count == 0:
            last_modified = None
        new_records = self.get_collection_records(last_modified)

        # Update the remote collection.
        with self.remote.batch() as batch:
            for record in new_records:
                batch.update_record(data=record, id=record['id'], safe=False)
            batch.patch_collection(data={'signature': signature})
