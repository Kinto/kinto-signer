import mock
from cliquet.storage import Filter
from cliquet.utils import COMPARISON

from kinto_signer import LocalUpdater
from .support import unittest


class LocalUpdaterTest(unittest.TestCase):

    def setUp(self):
        self.storage = mock.MagicMock()
        self.signer_instance = mock.MagicMock()
        self.updater = LocalUpdater(
            source={
                'bucket': 'localbucket',
                'collection': 'localcollection'},
            destination={
                'bucket': 'destbucket',
                'collection': 'destcollection'},
            signer=self.signer_instance,
            storage=self.storage)

    def test_get_local_records_asks_storage_for_records(self):
        records = mock.sentinel.records
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_local_records()
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/localbucket/collections/localcollection')

    def test_get_local_records_asks_storage_for_last_modified_records(self):
        records = mock.sentinel.records
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_local_records(1234)
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/localbucket/collections/localcollection',
            filters=[Filter('last_modified', 1234, COMPARISON.GT)])

    def test_get_destination_last_modified(self):
        records = mock.sentinel.records
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)
        self.updater.get_destination_last_modified()
        self.storage.collection_timestamp.assert_called_with(
            collection_id='record',
            parent_id='/buckets/destbucket/collections/destcollection')
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/destbucket/collections/destcollection')

    def test_push_records_to_destination(self):
        self.updater.get_destination_last_modified = mock.MagicMock(
            return_value=(1324, 10))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 4)]
        self.updater.get_local_records = mock.MagicMock(return_value=records)
        self.updater.push_records_to_destination()
        assert self.storage.update.call_count == 3

    @unittest.skip("not currently implemented")
    def test_push_records_removes_deleted_records(self):
        pass

    def test_push_records_to_destination_with_no_destination_changes(self):
        self.updater.get_destination_last_modified = mock.MagicMock(
            return_value=(1324, 0))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 4)]
        self.updater.get_local_records = mock.MagicMock(return_value=records)
        self.updater.push_records_to_destination()
        self.updater.get_local_records.assert_called_with(None)
        assert self.storage.update.call_count == 3

    def test_set_destination_signature_modifies_the_local_collection(self):
        self.storage.get.return_value = {'id': 1234}
        self.updater.set_destination_signature(mock.sentinel.signature)

        self.storage.update.assert_called_with(
            collection_id='collection',
            object_id='destcollection',
            parent_id='/buckets/destbucket',
            record={
                'id': 1234,
                'signature': mock.sentinel.signature
            })

    def test_sign_and_update_remote(self):
        records = [{'id': idx, 'foo': 'bar %s' % idx}
                   for idx in range(1, 3)]
        self.storage.get_all.return_value = (records, 2)
        self.updater.update_remote = mock.MagicMock()

        self.updater.get_local_records = mock.MagicMock()
        self.updater.push_records_to_destination = mock.MagicMock()
        self.updater.set_destination_signature = mock.MagicMock()
        self.updater.sign_and_update_remote()

        assert self.updater.get_local_records.call_count == 1
        assert self.updater.push_records_to_destination.call_count == 1
        assert self.updater.set_destination_signature.call_count == 1
