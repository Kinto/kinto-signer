import mock
import pytest
from cliquet.storage import Filter
from cliquet.storage.exceptions import UnicityError
from cliquet.utils import COMPARISON

from kinto_signer.updater import LocalUpdater
from .support import unittest


class LocalUpdaterTest(unittest.TestCase):

    def setUp(self):
        self.storage = mock.MagicMock()
        self.permission = mock.MagicMock()
        self.signer_instance = mock.MagicMock()
        self.updater = LocalUpdater(
            source={
                'bucket': 'localbucket',
                'collection': 'localcollection'},
            destination={
                'bucket': 'destbucket',
                'collection': 'destcollection'},
            signer=self.signer_instance,
            storage=self.storage,
            permission=self.permission)

    def patch(self, obj, *args, **kwargs):
        patcher = mock.patch.object(obj, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_updater_raises_if_resources_are_not_set_properly(self):
        with pytest.raises(ValueError) as excinfo:
            LocalUpdater(
                source={'bucket': 'local'},
                destination={},
                signer=self.signer_instance,
                storage=self.storage,
                permission=self.permission)
        assert str(excinfo.value) == ("Resources should contain both "
                                      "bucket and collection")

    def test_get_local_records_asks_storage_for_records(self):
        records = mock.sentinel.records
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_local_records()
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/localbucket/collections/localcollection',
            include_deleted=False)

    def test_get_local_records_asks_storage_for_last_modified_records(self):
        records = mock.sentinel.records
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_local_records(1234)
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/localbucket/collections/localcollection',
            include_deleted=False,
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
        self.patch(self.updater, 'get_destination_last_modified',
                   return_value=(1324, 10))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 4)]
        self.patch(self.updater, 'get_local_records',  return_value=records)
        self.updater.push_records_to_destination()
        assert self.storage.update.call_count == 3

    def test_push_records_removes_deleted_records(self):
        self.patch(self.updater, 'get_destination_last_modified',
                   return_value=(1324, 10))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(0, 2)]
        records.extend([{'id': idx, 'deleted': True} for idx in range(3, 5)])
        self.patch(self.updater, 'get_local_records', return_value=records)
        self.updater.push_records_to_destination()
        self.updater.get_local_records.assert_called_with(
            1324, include_deleted=True)
        assert self.storage.update.call_count == 2
        assert self.storage.delete.call_count == 2

    def test_push_records_to_destination_with_no_destination_changes(self):
        self.patch(self.updater, 'get_destination_last_modified',
                   return_value=(1324, 0))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 4)]
        self.patch(self.updater, 'get_local_records', return_value=records)
        self.updater.push_records_to_destination()
        self.updater.get_local_records.assert_called_with(
            None, include_deleted=True)
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

    def test_update_source_status_modifies_the_local_collection(self):
        self.storage.get.return_value = {'id': 1234, 'status': 'to-sign'}
        self.updater.update_source_status("signed")

        self.storage.update.assert_called_with(
            collection_id='collection',
            object_id='localcollection',
            parent_id='/buckets/localbucket',
            record={
                'id': 1234,
                'status': "signed"
            })

    def test_create_destination_updates_collection_permissions(self):
        collection_id = '/buckets/destbucket/collections/destcollection'
        self.updater.create_destination()
        self.permission.replace_object_permissions.assert_called_with(
            collection_id,
            {"read": ("system.Everyone",)})

    def test_create_destination_creates_bucket(self):
        self.updater.create_destination()
        self.storage.create.assert_any_call(
            collection_id='bucket',
            parent_id='',
            record={"id": 'destbucket'})

    def test_create_destination_creates_collection(self):
        bucket_id = '/buckets/destbucket'
        self.updater.create_destination()
        self.storage.create.assert_any_call(
            collection_id='collection',
            parent_id=bucket_id,
            record={"id": 'destcollection'})

    def test_ensure_resource_exists_handles_uniticy_errors(self):
        self.storage.create.side_effect = UnicityError('id', 'record')
        self.updater._ensure_resource_exists('bucket', '', 'abcd')

    def test_sign_and_update_remote(self):
        records = [{'id': idx, 'foo': 'bar %s' % idx}
                   for idx in range(1, 3)]
        self.storage.get_all.return_value = (records, 2)

        self.patch(self.storage, 'update_remote')
        self.patch(self.updater, 'get_local_records')
        self.patch(self.updater, 'push_records_to_destination')
        self.patch(self.updater, 'set_destination_signature')
        self.updater.sign_and_update_remote()

        assert self.updater.get_local_records.call_count == 1
        assert self.updater.push_records_to_destination.call_count == 1
        assert self.updater.set_destination_signature.call_count == 1
