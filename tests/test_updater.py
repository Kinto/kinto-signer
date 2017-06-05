import mock
import pytest
import unittest

from kinto.core.storage import Filter, Sort
from kinto.core.storage.exceptions import UnicityError, RecordNotFoundError
from kinto.core.utils import COMPARISON

from kinto_signer.updater import LocalUpdater
from kinto_signer.utils import STATUS

from .support import DummyRequest


class LocalUpdaterTest(unittest.TestCase):

    def setUp(self):
        self.storage = mock.MagicMock()
        self.permission = mock.MagicMock()
        self.signer_instance = mock.MagicMock()
        self.updater = LocalUpdater(
            source={
                'bucket': 'sourcebucket',
                'collection': 'sourcecollection'},
            destination={
                'bucket': 'destbucket',
                'collection': 'destcollection'},
            signer=self.signer_instance,
            storage=self.storage,
            permission=self.permission)

        # Resource events are bypassed completely in this test suite.
        patcher = mock.patch('kinto_signer.updater.build_request')
        self.addCleanup(patcher.stop)
        patcher.start()

    def patch(self, obj, *args, **kwargs):
        patcher = mock.patch.object(obj, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_updater_raises_if_resources_are_not_set_properly(self):
        with pytest.raises(ValueError) as excinfo:
            LocalUpdater(
                source={'bucket': 'source'},
                destination={},
                signer=self.signer_instance,
                storage=self.storage,
                permission=self.permission)
        assert str(excinfo.value) == ("Resources should contain both "
                                      "bucket and collection")

    def test_get_source_records_asks_storage_for_records(self):
        records = []
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_source_records(None)
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/sourcebucket/collections/sourcecollection',
            include_deleted=True,
            sorting=[Sort('last_modified', 1)])

    def test_get_source_records_asks_storage_for_last_modified_records(self):
        records = []
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)

        self.updater.get_source_records(1234)
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/sourcebucket/collections/sourcecollection',
            include_deleted=True,
            filters=[Filter('last_modified', 1234, COMPARISON.GT)],
            sorting=[Sort('last_modified', 1)])

    def test_get_destination_records(self):
        # We want to test get_destination_records with some records.
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 4)]
        count = mock.sentinel.count
        self.storage.get_all.return_value = (records, count)
        self.updater.get_destination_records()
        self.storage.collection_timestamp.assert_called_with(
            collection_id='record',
            parent_id='/buckets/destbucket/collections/destcollection')
        self.storage.get_all.assert_called_with(
            collection_id='record',
            parent_id='/buckets/destbucket/collections/destcollection',
            include_deleted=True,
            sorting=[Sort('last_modified', 1)])

    def test_push_records_to_destination(self):
        self.patch(self.updater, 'get_destination_records',
                   return_value=([], 1324))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 4)]
        self.patch(self.updater, 'get_source_records',
                   return_value=(records, 1325))
        self.updater.push_records_to_destination(DummyRequest())
        assert self.storage.update.call_count == 3

    def test_push_records_to_destination_raises_if_storage_is_misconfigured(self):
        self.patch(self.updater, 'get_destination_records',
                   return_value=([], 1324))
        self.patch(self.updater, 'get_source_records',
                   return_value=([], 1234))
        with pytest.raises(ValueError):
            self.updater.push_records_to_destination(DummyRequest())

    def test_push_records_removes_deleted_records(self):
        self.patch(self.updater, 'get_destination_records',
                   return_value=([], 1324))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(0, 2)]
        records.extend([{'id': idx, 'deleted': True, 'last_modified': 42}
                        for idx in range(3, 5)])
        self.patch(self.updater, 'get_source_records',
                   return_value=(records, 1325))
        self.updater.push_records_to_destination(DummyRequest())
        self.updater.get_source_records.assert_called_with(last_modified=1324)
        assert self.storage.update.call_count == 2
        assert self.storage.delete.call_count == 2

    def test_push_records_skip_already_deleted_records(self):
        # In case the record doesn't exists in the destination
        # a RecordNotFoundError is raised.
        self.storage.delete.side_effect = RecordNotFoundError()
        self.patch(self.updater, 'get_destination_records',
                   return_value=([], 1324))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(0, 2)]
        records.extend([{'id': idx, 'deleted': True, 'last_modified': 42}
                       for idx in range(3, 5)])
        self.patch(self.updater, 'get_source_records',
                   return_value=(records, 1325))
        # Calling the updater should not raise the RecordNotFoundError.
        self.updater.push_records_to_destination(DummyRequest())

    def test_push_records_to_destination_with_no_destination_changes(self):
        self.patch(self.updater, 'get_destination_records',
                   return_value=([], None))
        records = [{'id': idx, 'foo': 'bar %s' % idx} for idx in range(1, 4)]
        self.patch(self.updater, 'get_source_records',
                   return_value=(records, 1325))
        self.updater.push_records_to_destination(DummyRequest())
        self.updater.get_source_records.assert_called_with(last_modified=None)
        assert self.storage.update.call_count == 3

    def test_set_destination_signature_modifies_the_destination_collection(self):
        self.storage.get.return_value = {'id': 1234, 'last_modified': 1234}
        self.updater.set_destination_signature(mock.sentinel.signature,
                                               {},
                                               DummyRequest())

        self.storage.update.assert_called_with(
            collection_id='collection',
            object_id='destcollection',
            parent_id='/buckets/destbucket',
            record={
                'id': 1234,
                'signature': mock.sentinel.signature
            })

    def test_set_destination_signature_copies_kinto_admin_ui_fields(self):
        self.storage.get.return_value = {'id': 1234, 'sort': '-age', 'last_modified': 1234}
        self.updater.set_destination_signature(mock.sentinel.signature,
                                               {'displayFields': ['name'], 'sort': 'size'},
                                               DummyRequest())

        self.storage.update.assert_called_with(
            collection_id='collection',
            object_id='destcollection',
            parent_id='/buckets/destbucket',
            record={
                'id': 1234,
                'signature': mock.sentinel.signature,
                'sort': '-age',
                'displayFields': ['name']
            })

    def test_update_source_status_modifies_the_source_collection(self):
        self.storage.get.return_value = {'id': 1234, 'last_modified': 1234,
                                         'status': 'to-sign'}
        self.updater.update_source_status(STATUS.SIGNED, DummyRequest())

        self.storage.update.assert_called_with(
            collection_id='collection',
            object_id='sourcecollection',
            parent_id='/buckets/sourcebucket',
            record={
                'id': 1234,
                'last_reviewer': 'basicauth:bob',
                'status': "signed"
            })

    def test_create_destination_updates_collection_permissions(self):
        collection_id = '/buckets/destbucket/collections/destcollection'
        self.updater.create_destination(DummyRequest())
        self.permission.replace_object_permissions.assert_called_with(
            collection_id,
            {"read": ("system.Everyone",)})

    def test_create_destination_creates_bucket(self):
        self.updater.create_destination(DummyRequest())
        self.storage.create.assert_any_call(
            collection_id='bucket',
            parent_id='',
            record={"id": 'destbucket'})

    def test_create_destination_creates_collection(self):
        bucket_id = '/buckets/destbucket'
        self.updater.create_destination(DummyRequest())
        self.storage.create.assert_any_call(
            collection_id='collection',
            parent_id=bucket_id,
            record={"id": 'destcollection'})

    def test_ensure_resource_exists_handles_uniticy_errors(self):
        self.storage.create.side_effect = UnicityError('id', 'record')
        self.updater._ensure_resource_exists('bucket', '', 'abcd',
                                             DummyRequest())

    def test_sign_and_update_destination(self):
        records = [{'id': idx, 'foo': 'bar %s' % idx, 'last_modified': idx}
                   for idx in range(1, 3)]
        self.storage.get_all.return_value = (records, 2)

        self.patch(self.storage, 'update_records')
        self.patch(self.updater, 'get_destination_records',
                   return_value=([], '0'))
        self.patch(self.updater, 'push_records_to_destination')
        self.patch(self.updater, 'set_destination_signature')
        self.patch(self.updater, 'invalidate_cloudfront_cache')
        self.updater.sign_and_update_destination(DummyRequest(), {'id': 'source'})

        assert self.updater.get_destination_records.call_count == 1
        assert self.updater.push_records_to_destination.call_count == 1
        assert self.updater.set_destination_signature.call_count == 1
        assert self.updater.invalidate_cloudfront_cache.call_count == 1

    def test_if_distribution_id_a_cloudfront_invalidation_request_is_triggered(self):
        request = mock.MagicMock()
        request.registry.settings = {'signer.distribution_id': 'DWIGHTENIS'}
        with mock.patch('boto3.client') as boto3_client:
            self.updater.invalidate_cloudfront_cache(request, 'tz_1234')
            boto3_client.return_value.create_invalidation.assert_called_with(
                DistributionId='DWIGHTENIS',
                InvalidationBatch={
                    'CallerReference': 'tz_1234',
                    'Paths': {
                        'Quantity': 1,
                        'Items': ['/v1//buckets/destbucket/collections/destcollection*']}})
