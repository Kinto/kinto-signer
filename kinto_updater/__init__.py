import copy
import hashlib
import json
import operator
import uuid

from kinto_client import Client

import signing


class UpdaterException(Exception):
    pass


class Updater(object):

    def __init__(self, bucket, collection, server_url=None,
                 auth=None, session=None, endpoints=None,
                 signer=None, settings=None):
        self.client = Client(
            bucket=bucket, collection=collection,
            server_url=server_url, session=session)

        if settings is None:
            settings = {}
        self.settings = settings

        if signer is None:
            signer = signing.RSABackend(self.settings)
        self.signer = signer

        self.bucket = bucket
        self.collection = collection

    def gather_remote_collection(self):
        '''Retrieves the remote collection and returns it.'''
        collection = self.client.get_collection()
        records = {record['id']: record
                   for record in self.client.get_records()}

        return records, collection['data']

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

        with self.client.batch() as batch:
            # Create IDs for records which don't already have one.
            for record in new_records:

                if 'id' not in record:
                    record['id'] = str(uuid.uuid4())
                    batch.create_record(id=record['id'], data=record)
                else:
                    batch.update_record(id=record['id'], data=record)

            # Compute the hash of the old + new records
            records.update({record['id']: record
                            for record in new_records})
            new_hash = compute_hash(records.values())
            signature = self.signer.sign(new_hash)

            # Send the new hash + signature to the remote.
            batch.patch_collection(data={'signature': signature})


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
