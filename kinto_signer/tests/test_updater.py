from cliquet.storage import Filter
from cliquet.utils import COMPARISON

from .support import unittest

from kinto_client import Client
from kinto_signer import RemoteUpdater
import mock

SERVER_URL = "http://kinto-storage.org"


class BaseUpdaterTest(object):
    def _build_response(self, data, headers=None):
        if headers is None:
            headers = {}
        resp = {
            'data': data
        }
        return resp, headers


class RemoteUpdaterTest(unittest.TestCase):

    def setUp(self):
        self.session = mock.MagicMock()
        self.remote = Client(
            bucket="buck",
            collection="coll",
            session=self.session)
        self.storage = mock.MagicMock()
        self.signer_instance = mock.MagicMock()
        self.updater = RemoteUpdater(
            remote=self.remote,
            signer=self.signer_instance,
            storage=self.storage,
            bucket_id='bucket',
            collection_id='collection')

    def test_collection_records_asks_storage_for_records(self):
        records = mock.sentinel.records
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_collection_records()
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/bucket/collections/collection')

    def test_collection_records_asks_storage_for_last_modified_records(self):
        records = mock.sentinel.records
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_collection_records(1234)
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/bucket/collections/collection',
            filters=[Filter('last_modified', 1234, COMPARISON.GT)])

    def test_get_remote_last_modified(self):
        headers = {'Etag': '"1234"'}
        self.remote.session.request.return_value = (None, headers)
        self.updater.get_remote_last_modified()
        self.remote.session.request.assert_called_with(
            'get', '/buckets/buck/collections/coll/records')

    def test_update_remote(self):
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 3)]
        self.updater.get_remote_last_modified = mock.MagicMock(
            return_value=1234)
        self.updater.get_collection_records = mock.MagicMock(
            return_value=records)

        batch = mock.MagicMock()
        self.remote.batch = mock.MagicMock(return_value=batch)
        self.updater.update_remote("hash", "signature")

        batch.__enter__().update_record.assert_any_call(
            data={'foo': 'bar 2', 'id': 2}, id=2, safe=False)
        batch.__enter__().update_record.assert_any_call(
            data={'foo': 'bar 1', 'id': 1}, id=1, safe=False)
        batch.__enter__().patch_collection.assert_called_with(
            data={'signature': 'signature'})

    def test_sign_and_update_remote(self):
        records = [{'id': idx, 'foo': 'bar %s' % idx}
                   for idx in range(1, 3)]
        self.storage.get_all.return_value = (records, 2)
        self.updater.update_remote = mock.MagicMock()

        self.updater.sign_and_update_remote()
