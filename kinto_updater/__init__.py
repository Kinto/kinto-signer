import copy
import hashlib
import json
import operator
import uuid
import urlparse

import kinto_client
from kinto_client import batch_requests

import signing


class UpdaterException(Exception):
    pass


class Updater(object):

    def __init__(self, bucket, collection, auth=None,
                 server_url=kinto_client.DEFAULT_SERVER_URL,
                 session=None, endpoints=None,
                 signer=None, settings=None):
        if session is None and auth is None:
            raise ValueError('session or auth should be defined')
        if session is None:
            session = kinto_client.create_session(server_url, auth)
        self.session = session

        if settings is None:
            settings = {}
        self.settings = settings

        if signer is None:
            signer = signing.RSABackend(self.settings)
        self.signer = signer

        if endpoints is None:
            endpoints = kinto_client.Endpoints()
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
            if 'signature' not in collection_data:
                raise UpdaterException("Unable to verify unsigned data")
            signature = collection_data['signature']
            self.check_data_validity(records, signature)

        with batch_requests(self.session, self.endpoints) as batch:
            # Create IDs for records which don't already have one.
            for record in new_records:
                headers = {}
                if 'id' not in record:
                    record['id'] = str(uuid.uuid4())
                headers['If-None-Match'] = '*'

                record_endpoint = self.endpoints.record(
                    self.bucket, self.collection, record['id'])

                batch.add('PUT', record_endpoint, data=record, headers=headers)

            # Compute the hash of the old + new records
            records.update({record['id']: record
                            for record in new_records})
            new_hash = compute_hash(records.values())
            signature = self.signer.sign(new_hash)

            # Send the new hash + signature to the remote.
            batch.add(
                'PATCH',
                self.endpoints.collection(self.bucket, self.collection),
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
