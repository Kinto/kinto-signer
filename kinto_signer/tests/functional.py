import os.path
import time
from six.moves.urllib.parse import urljoin

import unittest2
import requests
from six.moves import configparser

from kinto_signer.serializer import canonical_json
from kinto_signer.signer.local_ecdsa import ECDSASigner

from kinto_client import Client

__HERE__ = os.path.abspath(os.path.dirname(__file__))

SERVER_URL = "http://localhost:8888/v1"
DEFAULT_AUTH = ('user', 'p4ssw0rd')


class FunctionalTest(unittest2.TestCase):

    def __init__(self, *args, **kwargs):
        super(FunctionalTest, self).__init__(*args, **kwargs)
        self.auth = DEFAULT_AUTH
        self.private_key = os.path.join(__HERE__, 'config/ecdsa.private.pem')

        self.signer_config = configparser.RawConfigParser()
        self.signer_config.read(os.path.join(__HERE__, 'config/signer.ini'))
        priv_key = self.signer_config.get(
            'app:main', 'kinto.signer.ecdsa.private_key')
        self.signer = ECDSASigner(private_key=priv_key)

        # Setup the kinto clients for the source and destination.
        self._auth = DEFAULT_AUTH
        self._server_url = SERVER_URL
        self._source_bucket = "source"
        self._destination_bucket = "destination"
        self._collection_id = "collection1"

        self.source = Client(
            server_url=self._server_url,
            auth=self._auth,
            bucket=self._source_bucket,
            collection=self._collection_id)

        self.destination = Client(
            server_url=self._server_url,
            auth=self._auth,
            bucket=self._destination_bucket,
            collection=self._collection_id)

    def tearDown(self):
        # Delete all the created objects.
        self._flush_server(self._server_url)

    def _flush_server(self, server_url):
        flush_url = urljoin(server_url, '/__flush__')
        resp = requests.post(flush_url)
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

        # Ensure the remote data is signed properly.
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


if __name__ == '__main__':
    unittest2.main()
