import os.path
from six.moves.urllib.parse import urljoin

import unittest2
import requests
from six.moves import configparser

from kinto_signer.hasher import canonical_json
from kinto_signer import signer

from kinto_client.replication import replicate
from kinto_client import Client

__HERE__ = os.path.abspath(os.path.dirname(__file__))

SERVER_URL = "http://localhost:8888/v1"
DEFAULT_AUTH = ('user', 'p4ssw0rd')


class FunctionalTest(unittest2.TestCase):

    def __init__(self, *args, **kwargs):
        super(FunctionalTest, self).__init__(*args, **kwargs)
        # Setup the private key and signer instance.
        self.private_key = os.path.join(__HERE__, 'config/test.pem')
        self.signer_config = configparser.RawConfigParser()
        self.signer_config.read(os.path.join(__HERE__, 'config/signer.ini'))
        priv_key = self.signer_config.get(
            'app:main', 'kinto_signer.private_key')
        self.signer = signer.ECDSABackend({'private_key': priv_key})

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
        # Delete all the created objects
        self._flush_server(self._server_url)

    def _flush_server(self, server_url):
        flush_url = urljoin(server_url, '/__flush__')
        resp = requests.post(flush_url)
        resp.raise_for_status()

    def test_signature_on_new_records(self):
        # Populate the destination with some data.
        with self.destination.batch() as batch:
            batch.create_bucket()
            batch.create_collection()
            for n in range(10):
                batch.create_record(data={'foo': 'bar', 'n': n})

        # Copy the data from the **destination** to the **source**.
        # This seems to be weird, but is actually what we want here, the
        # signer **hook** will take care of copying the new records to the
        # destination, later on.
        replicate(self.destination, self.source)

        # Check that the data has been copied.
        records = self.source.get_records()
        assert len(records) == 10

        # Send new data to the signer.
        with self.source.batch() as batch:
            for n in range(100, 105):
                batch.create_record(data={'newdata': n})

        # Trigger a signature.
        self.source.update_collection(
            data={'status': 'to-sign'},
            method="put")

        # Ensure the remote data is signed properly.
        data = self.destination.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        records = self.destination.get_records()
        assert len(records) == 15
        serialized_records = canonical_json(records)
        self.signer.verify(serialized_records, signature)

if __name__ == '__main__':
    unittest2.main()
