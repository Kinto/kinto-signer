import copy
import hashlib
import json
import operator
import uuid
import collections
from contextlib import contextmanager

import kintoclient


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
        resp = self.session.request(
            'POST',
            self.endpoints.batch(),
            data={'requests': self._build_requests()}
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

    def batch(self):
        return '{root}/batch'.format(root=self.root)

    def root(self):
        return '{root}/'.format(root=self.root)


class Updater(object):

    def __init__(self, bucket, collection, auth=None,
                 server_url=kintoclient.DEFAULT_SERVER_URL,
                 session=None, endpoints=None):
        if session is None and auth is None:
            raise ValueError('session or auth should be defined')
        if session is None:
            session = kintoclient.create_session(server_url, auth)
        if endpoints is None:
            endpoints = Endpoints()
        self.session = session
        self.endpoints = endpoints
        self.bucket = bucket
        self.collection = collection
        self.server_url = server_url

    def gather_remote_collection(self):
        '''Retrieves the remote collection and returns it.'''
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
            message = 'The local hash differs from the remote one. Aborting.'
            raise ValueError(message)

    def add_records(self, new_records):
        new_records = copy.deepcopy(new_records)
        records, collection_data = self.gather_remote_collection()

        if records:
            remote_hash = collection_data['hash']
            signature = collection_data['signature']
            self.check_data_validity(records, remote_hash, signature)

        with batch_requests(self.session, self.endpoints) as batch:
            # Create IDs for records which don't already have one.
            for record in new_records:
                if 'id' not in record:
                    record['id'] = uuid.uuid4()

                record_endpoint = self.endpoints.record(
                    self.bucket, self.collection, record['id'])

                batch.add('PUT', record_endpoint, data=record)

                # Compute the hash of the old + new records
                # Sign it.
                # XXX Do it with trunion
                records.extend(new_records)
                hash_ = compute_hash(records)

                # Send the new hash + signature to the remote.
                batch.add(
                    'PUT',
                    self.endpoints.records(self.bucket, self.collection),
                    data={'hash': hash_})

def compute_hash(records):
    records = copy.deepcopy(records)

    for record in records:
        del record['last_modified']

    records = sorted(records, key=operator.itemgetter('id'))

    serialized = json.dumps(records, sort_keys=True)
    print(serialized)
    h = hashlib.new('sha256')
    h.update(serialized)
    return h.hexdigest()


def main():
    updater = Updater('default', 'items', auth=('user', 'pass'),
                      server_url='http://localhost:8888/v1')
    new_records = [
        {'data': 'foo'},
        {'data': 'bar'},
        {'data': 'baz'}
    ]
    updater.add_records(new_records)


if __name__ == '__main__':
    main()
