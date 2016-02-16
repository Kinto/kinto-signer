import os.path
from six.moves.urllib.parse import urljoin

import unittest2
import requests
from six.moves import configparser

from cliquet import utils as cliquet_utils

from kinto_signer.hasher import compute_hash
from kinto_signer import signer

from kinto_client.replication import replicate
from kinto_client import Client

__HERE__ = os.path.abspath(os.path.dirname(__file__))

SIGNER_URL = "http://localhost:8888/v1"
REMOTE_URL = "http://localhost:7777/v1"
DEFAULT_AUTH = ('user', 'p4ssw0rd')


class FunctionalTest(unittest2.TestCase):

    def __init__(self, *args, **kwargs):
        super(FunctionalTest, self).__init__(*args, **kwargs)
        # XXX Read the configuration from env variables.
        self.auth = DEFAULT_AUTH
        self.private_key = os.path.join(__HERE__, 'config/test.pem')

        self.signer_url = SIGNER_URL
        self.signer_config = configparser.RawConfigParser()
        self.signer_config.read(os.path.join(__HERE__, 'config/signer.ini'))
        self.signer_client = Client(
            server_url=self.signer_url,
            auth=self.auth,
            bucket="buck",
            collection="coll")

        self.remote_url = REMOTE_URL
        self.remote_config = configparser.RawConfigParser()
        self.remote_config.read(os.path.join(__HERE__, 'config/remote.ini'))
        self.remote_client = Client(
            server_url=self.remote_url,
            auth=self.auth,
            bucket="buck",
            collection="coll")

        priv_key = self.signer_config.get(
            'app:main', 'kinto_signer.private_key')
        self.signer = signer.ECDSABackend({'private_key': priv_key})

    def tearDown(self):
        # Delete all the created objects
        self.flush_server(self.signer_url)
        self.flush_server(self.remote_url)

    def flush_server(self, server_url):
        flush_url = urljoin(server_url, '/__flush__')
        resp = requests.post(flush_url)
        resp.raise_for_status()

    def get_user_id(self, credentials):
        hmac_secret = self.signer_config.get(
            'app:main',
            'cliquet.userid_hmac_secret')
        credentials = '%s:%s' % credentials
        digest = cliquet_utils.hmac_digest(hmac_secret, credentials)
        return 'basicauth:%s' % digest

    def test_signature_on_new_records(self):
        # Populate the remote server with some data.
        with self.remote_client.batch() as batch:
            batch.create_bucket()
            batch.create_collection()
            for n in range(10):
                batch.create_record(data={'foo': 'bar', 'n': n})

        # Replicate the remote data locally:
        origin = Client(
            server_url=self.remote_url,
            auth=self.auth,
            bucket='buck',
            collection='coll'
        )
        authority = Client(
            server_url=self.signer_url,
            auth=self.auth,
            bucket='buck',
            collection='coll')

        replicate(origin, authority)

        # Check that the data has been copied.
        records = self.signer_client.get_records()
        assert len(records) == 10

        # Send new data to the signer.
        with self.signer_client.batch() as batch:
            for n in range(100, 105):
                batch.create_record(data={'newdata': n})
        self.signer_client.update_collection(
            data={'status': 'to-sign'},
            method="put")

        # Ensure the remote data is signed properly.
        data = self.remote_client.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        records = self.remote_client.get_records()
        assert len(records) == 15
        local_hash = compute_hash(records)
        self.signer.verify(local_hash, signature)

    def test_signature_on_local_collections(self):
        # Replicate the remote data locally:
        origin = Client(
            server_url=self.signer_url,
            auth=self.auth,
            bucket='buck',
            collection='destination'
        )
        authority = Client(
            server_url=self.signer_url,
            auth=self.auth,
            bucket='buck',
            collection='origin')

        # Populate the origin with some data.
        with origin.batch() as batch:
            batch.create_bucket()
            batch.create_collection()
            for n in range(10):
                batch.create_record(data={'foo': 'bar', 'n': n})

        replicate(origin, authority)

        # Check that the data has been copied.
        records = authority.get_records()
        assert len(records) == 10

        # Send new data to the signer.
        with authority.batch() as batch:
            for n in range(100, 105):
                batch.create_record(data={'newdata': n})

        authority.update_collection(
            data={'status': 'to-sign'},
            method="put")

        # Ensure the remote data is signed properly.
        data = origin.get_collection()
        signature = data['data']['signature']
        assert signature is not None

        records = origin.get_records()
        assert len(records) == 15
        local_hash = compute_hash(records)
        self.signer.verify(local_hash, signature)

if __name__ == '__main__':
    unittest2.main()
