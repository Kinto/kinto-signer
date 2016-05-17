import os.path
import time
from six.moves.urllib.parse import urljoin

import unittest2
import requests

from kinto_signer.serializer import canonical_json
from kinto_signer.signer import local_ecdsa

from kinto_client import Client

__HERE__ = os.path.abspath(os.path.dirname(__file__))

SERVER_URL = "http://localhost:8888/v1"
DEFAULT_AUTH = ('user', 'p4ssw0rd')


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

    def _flush_server(self, server_url):
        flush_url = urljoin(self.server_url, '/__flush__')
        resp = requests.post(flush_url)
        resp.raise_for_status()

    def test_heartbeat_is_successful(self):
        hb_url = urljoin(self.server_url, '/__heartbeat__')
        resp = requests.get(hb_url)
        resp.raise_for_status()

    def test_destination_creation_and_new_records_signature(self):
        self.source.create_bucket()
        self.source.create_collection()

        # Send new data to the signer.
        with self.source.batch() as batch:
            for n in range(0, 10):
                batch.create_record(data={'newdata': n})

        source_records = self.source.get_records()
        assert len(source_records) == 10

        # Trigger a signature.
        self.source.update_collection(
            data={'status': 'to-sign'},
            method="put")

        # Ensure the destination data is signed properly.
        data = self.destination.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        records = self.destination.get_records()
        assert len(records) == 10
        serialized_records = canonical_json(records)
        self.signer.verify(serialized_records, signature)

        # the status of the source collection should be "signed".
        source_collection = self.source.get_collection()['data']
        assert source_collection['status'] == 'signed'

    def test_records_deletion_and_signature(self):
        self.source.create_bucket()
        self.source.create_collection()

        # Create some data on the source collection and send it.
        with self.source.batch() as batch:
            for n in range(0, 10):
                batch.create_record(data={'newdata': n})

        source_records = self.source.get_records()
        assert len(source_records) == 10

        # Trigger a signature.
        self.source.update_collection(data={'status': 'to-sign'}, method="put")

        # Wait so the new last_modified timestamp will be greater than the
        # one from the previous records.
        time.sleep(0.01)
        # Now delete one record on the source and trigger another signature.
        self.source.delete_record(source_records[0]['id'])
        self.source.update_collection(data={'status': 'to-sign'}, method="put")

        records = self.destination.get_records()
        assert len(records) == 9

        data = self.destination.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        serialized_records = canonical_json(records)
        # This raises when the signature is invalid.
        self.signer.verify(serialized_records, signature)


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
