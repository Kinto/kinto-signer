import collections
import copy
import hashlib
import json
import operator
import uuid
import urlparse
from contextlib import contextmanager

import kintoclient

import signing


@contextmanager
def batch_requests(session, endpoints):
    batch = Batch(session, endpoints)
    yield batch
    batch.send()


class Batch(object):

    def __init__(self, session, endpoints):
        self.session = session
        self.endpoints = endpoints
        self.requests = []

    def add(self, method, url, data=None, permissions=None):
        # Store all the requests in a dict, to be read later when .send()
        # is called.
        self.requests.append((method, url, data, permissions))

    def _build_requests(self):
        requests = []
        for (method, url, data, permissions) in self.requests:
            request = {
                'method': method,
                'path': url}

            request['body'] = {}
            if data is not None:
                request['body']['data'] = data
            if permissions is not None:
                request['body']['permissions'] = permissions
            requests.append(request)
        return requests

    def send(self):
        requests = self._build_requests()
        resp = self.session.request(
            'POST',
            self.endpoints.batch(),
            data={'requests': requests}
        )
        self.requests = []
        return resp


class Endpoints(object):
    def __init__(self, root=''):
        self.root = root

    def collection(self, bucket, coll):
        return ('{root}/buckets/{bucket}/collections/{coll}'
                .format(root=self.root, bucket=bucket, coll=coll))

    def records(self, bucket, coll):
        return ('{root}/buckets/{bucket}/collections/{coll}/records'
                .format(root=self.root, bucket=bucket, coll=coll))

    def record(self, bucket, coll, record_id):
        return ('{root}/buckets/{bucket}/collections/{coll}/records/{rid}'
                .format(root=self.root, bucket=bucket, coll=coll,
                        rid=record_id))

    def batch(self):
        return '{root}/batch'.format(root=self.root)

    def root(self):
        return '{root}/'.format(root=self.root)


class Updater(object):

    def __init__(self, bucket, collection, auth=None,
                 server_url=kintoclient.DEFAULT_SERVER_URL,
                 session=None, endpoints=None,
                 signer=None, settings=None):
        if session is None and auth is None:
            raise ValueError('session or auth should be defined')
        if session is None:
            session = kintoclient.create_session(server_url, auth)
        self.session = session

        if settings is None:
            settings = {}
        self.settings = settings

        if signer is None:
            signer = signing.RSABackend(self.settings)
        self.signer = signer

        if endpoints is None:
            endpoints = Endpoints()
        self.endpoints = endpoints

        self.bucket = bucket
        self.collection = collection
        self.server_url = server_url

    def gather_remote_collection(self):
        '''Retrieves the remote collection and returns it.'''
        coll_url = self.endpoints.collection(self.bucket, self.collection)
        collection_resp, _ = self.session.request('get', coll_url)

        def _get_records(records=None, url=None):
            if records is None:
                records = {}

            if url is None:
                url = self.endpoints.records(self.bucket, self.collection)
            record_resp, headers = self.session.request('get', url)

            records.update({record['id']: record
                            for record in record_resp['data']})

            if 'Next-Page' in headers.keys():
                parsed = urlparse.urlparse(headers['Next-Page'])
                url = "{0}?{1}".format(parsed.path, parsed.query)
                return _get_records(records, url=url)
            return records

        records = _get_records()
        return records, collection_resp['data']

    def check_data_validity(self, records, signature):
        local_hash = compute_hash(records.values())
        self.signer.verify(local_hash, signature)

    def add_records(self, new_records):
        new_records = copy.deepcopy(new_records)
        records, collection_data = self.gather_remote_collection()

        if records:
            remote_hash = collection_data['hash']
            signature = collection_data['signature']
            self.check_data_validity(records, signature)

        with batch_requests(self.session, self.endpoints) as batch:
            # Create IDs for records which don't already have one.
            for record in new_records:
                if 'id' not in record:
                    record['id'] = str(uuid.uuid4())

                record_endpoint = self.endpoints.record(
                    self.bucket, self.collection, record['id'])

                batch.add('PUT', record_endpoint, data=record)

            # Compute the hash of the old + new records
            records.update({record['id']: record
                            for record in new_records})
            new_hash = compute_hash(records.values())
            signature = self.signer.sign(new_hash)

            # Send the new hash + signature to the remote.
            batch.add(
                'PUT',
                self.endpoints.records(self.bucket, self.collection),
                data={'signature': signature}
            )

def compute_hash(records):
    records = copy.deepcopy(records)
    for record in records:
        if 'last_modified' in record.keys():
            del record['last_modified']

    records = sorted(records, key=operator.itemgetter('id'))

    serialized = json.dumps(records, sort_keys=True)
    print(serialized)
    h = hashlib.new('sha256')
    h.update(serialized)
    return h.hexdigest()

def generate_key():
    signer = signing.RSABackend()
    return signer.generate_key()

def add_new_items(items, settings):
    updater = Updater('default', 'items', auth=('user', 'pass'),
                      server_url='http://localhost:8888/v1',
                      settings=settings)
    updater.add_records(items)

def main():
    #print generate_key()
    items = [
        {'data': 'foo'},
        {'data': 'bar'},
        {'data': 'baz'}
    ]
    add_new_items(items, {'private_key': 'test.pem'})




if __name__ == '__main__':
    main()
