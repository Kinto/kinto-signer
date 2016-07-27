import time
import os.path
from six.moves.urllib.parse import urljoin

import unittest2
import requests

from kinto_signer.serializer import canonical_json
from kinto_signer.signer import local_ecdsa

from kinto_client import Client

__HERE__ = os.path.abspath(os.path.dirname(__file__))

SERVER_URL = "http://localhost:8888/v1"
DEFAULT_AUTH = ('user', 'p4ssw0rd')


def collection_timestamp(client):
    # XXXX Waiting https://github.com/Kinto/kinto-http.py/issues/77
    endpoint = client.get_endpoint('records')
    record_resp, headers = client.session.request('get', endpoint)
    return headers.get('ETag', '').strip('"')


class BaseTestFunctional(object):
    @classmethod
    def setUpClass(cls):
        super(BaseTestFunctional, cls).setUpClass()
        cls.signer = local_ecdsa.ECDSASigner(private_key=cls.private_key)
        cls.server_url = SERVER_URL
        cls.source = Client(
            server_url=cls.server_url,
            auth=DEFAULT_AUTH,
            bucket=cls.source_bucket,
            collection=cls.source_collection)

        cls.destination = Client(
            server_url=cls.server_url,
            auth=DEFAULT_AUTH,
            bucket=cls.destination_bucket,
            collection=cls.destination_collection)

    def tearDown(self):
        # Delete all the created objects.
        self._flush_server(self.server_url)

    def setUp(self):
        # Give the permission to tigger signatures to anybody
        perms = {"write": ["system.Authenticated"]}
        self.source.create_bucket()
        self.source.create_collection(permissions=perms)

        # Create some data on the source collection and send it.
        with self.source.batch() as batch:
            for n in range(0, 10):
                batch.create_record(data={'newdata': n})

        self.source_records = self.source.get_records()
        assert len(self.source_records) == 10

        time.sleep(0.1)

        # Trigger a signature.
        self.source.update_collection(data={'status': 'to-sign'})

    def _flush_server(self, server_url):
        flush_url = urljoin(self.server_url, '/__flush__')
        resp = requests.post(flush_url)
        resp.raise_for_status()

    def test_heartbeat_is_successful(self):
        hb_url = urljoin(self.server_url, '/__heartbeat__')
        resp = requests.get(hb_url)
        resp.raise_for_status()

    def test_metadata_attributes(self):
        # Ensure the destination data is signed properly.
        destination_collection = self.destination.get_collection()['data']
        signature = destination_collection['signature']
        assert signature is not None

        # the status of the source collection should be "signed".
        source_collection = self.source.get_collection()['data']
        assert source_collection['status'] == 'signed'

        assert (collection_timestamp(self.destination) ==
                collection_timestamp(self.source))

    def test_destination_creation_and_new_records_signature(self):
        # Create some records and trigger another signature.
        self.source.create_record({'newdata': 'hello'})
        self.source.create_record({'newdata': 'bonjour'})

        time.sleep(0.1)

        self.source.update_collection(data={'status': 'to-sign'})

        data = self.destination.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        records = self.destination.get_records()
        assert len(records) == 12
        last_modified = collection_timestamp(self.destination)
        serialized_records = canonical_json(records, last_modified)
        # This raises when the signature is invalid.
        self.signer.verify(serialized_records, signature)

    def test_records_update_and_signature(self):
        # Update some records and trigger another signature.
        updated = self.source_records[5].copy()
        updated['newdata'] = 'bump'
        self.source.update_record(updated)
        updated = self.source_records[0].copy()
        updated['newdata'] = 'hoop'
        self.source.update_record(updated)

        time.sleep(0.1)

        self.source.update_collection(data={'status': 'to-sign'})

        data = self.destination.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        records = self.destination.get_records()
        assert len(records) == 10
        last_modified = collection_timestamp(self.destination)
        serialized_records = canonical_json(records, last_modified)
        # This raises when the signature is invalid.
        self.signer.verify(serialized_records, signature)

    def test_records_deletion_and_signature(self):
        # Now delete one record on the source and trigger another signature.
        self.source.delete_record(self.source_records[1]['id'])
        self.source.delete_record(self.source_records[5]['id'])

        time.sleep(0.1)

        self.source.update_collection(data={'status': 'to-sign'})

        data = self.destination.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        records = self.destination.get_records(_since=0)  # obtain deleted too
        assert len(records) == 10  # two of them are deleted.
        last_modified = collection_timestamp(self.destination)
        serialized_records = canonical_json(records, last_modified)
        # This raises when the signature is invalid.
        self.signer.verify(serialized_records, signature)

    def test_distinct_users_can_trigger_signatures(self):
        collection = self.destination.get_collection()
        before = collection['data']['signature']

        self.source.create_record(data={"pim": "pam"})
        client = Client(
            server_url=self.server_url,
            auth=("Sam", "Wan-Elss"),
            bucket=self.source_bucket,
            collection=self.source_collection)
        # Trigger a signature as someone else.
        client.update_collection(data={'status': 'to-sign'})

        collection = self.destination.get_collection()
        after = collection['data']['signature']

        assert before != after


class AliceFunctionalTest(BaseTestFunctional, unittest2.TestCase):
    private_key = os.path.join(__HERE__, 'config/ecdsa.private.pem')
    source_bucket = "alice"
    destination_bucket = "alice"
    source_collection = "source"
    destination_collection = "destination"


# Signer is configured to use a different key for Bob and Alice.
class BobFunctionalTest(BaseTestFunctional, unittest2.TestCase):
    private_key = os.path.join(__HERE__, 'config/bob.ecdsa.private.pem')
    source_bucket = "bob"
    source_collection = "source"
    destination_bucket = "bob"
    destination_collection = "destination"


if __name__ == '__main__':
    unittest2.main()
