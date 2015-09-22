import kintoclient
import json
import hashlib


class Endpoints(object):
    def __init__(self, root=''):
        self.root = root

    def collection(self, bucket, coll):
        return ('{root}/buckets/{bucket}/collections/{coll}'
                .format(root=self.root, bucket=bucket, coll=coll))

    def records(self, bucket, coll):
        return ('{root}/buckets/{bucket}/collections/{coll}/records'
                .format(root=self.root, bucket=bucket, coll=coll))

    def root(self):
        return '{root}/'.format(root=self.root)


class Updater(object):

    def __init__(self, bucket, collection, auth=None,
                 server_url=kintoclient.DEFAULT_SERVER_URL,
                 session=None, endpoints=None):
        if session is None and auth is None:
            raise ValueError("session or auth should be defined")
        if session is None:
            session = kintoclient.create_session(server_url, auth)
        self.session = session
        if endpoints is None:
            endpoints = Endpoints()
        self.endpoints = endpoints
        self.bucket = bucket
        self.collection = collection
        self.server_url = server_url

    def gather_remote_collection(self):
        """Retrieves the remote collection and returns it."""
        collection_resp, _ = self.session.request(
            'get',
            self.endpoints.collection(self.bucket, self.collection))

        def _get_records(records=None, token=None):
            if records is None:
                records = []

            kwargs = {}
            if token is not None:
                kwargs['_token'] = token
            record_resp, headers = self.session.request(
                'get',
                self.endpoints.records(self.bucket, self.collection),
                **kwargs)

            records.extend(record_resp['data'])

            if 'Next-Page' in headers.keys():
                return _get_records(records, token=headers['Next-Page'])
            return records

        records = _get_records()
        return records, collection_resp['data']

    def check_data_validity(self, records, remote_hash, signature):
        # Check the validity of the signature.
        # XXX do it with trunion.
        local_hash = self.compute_hash(records)
        if local_hash != remote_hash:
            message = "The local hash differs from the remote one. Aborting."
            raise ValueError(message)

    def compute_hash(self, records):
        records = records.copy()

        for record in records:
            del record.last_modified

        serialized = json.dumps(records, sort_keys=True)
        h = hashlib.new('sha256')
        h.update(serialized)
        return h.hexdigest()

    def add(self, new_records):
        records, collection_data = self.gather_remote_collection()

        if records:
            remote_hash = collection_data['hash']
            signature = collection_data['signature']
            self.check_data_validity(records, remote_hash, signature)

        # Compute the hash of the old + new records
        # Sign it.
        # Send the new records and the new hash + signature to the remote.


def main():
    updater = Updater('default', 'items', auth=('user', 'pass'),
                      server_url='http://localhost:8888/v1')
    print(updater.gather_remote_collection())


if __name__ == '__main__':
    main()
