from .support import unittest

import kintoupdater
import kintoclient
import mock
import pytest


class UpdaterConstructorTest(unittest.TestCase):
    @mock.patch('kintoupdater.kintoclient.create_session')
    def test_session_is_defined_if_not_passed(self, create_session):
        kintoupdater.Updater(
            "bucket", "collection",
            auth=("user", "pass"))

        create_session.assert_called_with(kintoclient.DEFAULT_SERVER_URL,
                                          ('user', 'pass'))

    def test_session_is_used_if_passed(self):
        updater = kintoupdater.Updater(
            "bucket", "collection",
            session=mock.sentinel.session)
        assert updater.session == mock.sentinel.session

    def test_error_is_raised_on_missing_args(self):
        with pytest.raises(ValueError) as e:
            kintoupdater.Updater("bucket", "collection")
        assert "session or auth should be defined" in e.value

    @mock.patch('kintoupdater.Endpoints')
    def test_endpoints_is_created_by_constructor(self, endpoints):
        kintoupdater.Updater("bucket", "collection",
                             auth=("user", "pass"))
        endpoints.assert_called_with()

    def test_endpoints_is_used_if_passed(self):
        updater = kintoupdater.Updater("bucket", "collection",
                                       auth=("user", "pass"),
                                       endpoints=mock.sentinel.endpoints)
        assert updater.endpoints == mock.sentinel.endpoints


class UpdaterGatherRemoteCollectionTest(unittest.TestCase):

    def setUp(self):
        self._session = mock.MagicMock()

    def _get_response(self, data, headers=None):
        if headers is None:
            headers = {}
        resp = {
            'data': data
        }
        return resp, headers

    def test_pagination_is_followed(self):
        # Mock the calls to request.
        expected_collection_data = {'hash': 'super_hash', 'signature': 'sig'}
        self._session.request.side_effect = [
            # First one returns the collection information.
            self._get_response(expected_collection_data),
            # Second one returns a list of items with a pagination token.
            self._get_response(['item1', 'item2'], {'Next-Page': 'token'}),
            # Third one returns a list of items without a pagination token.
            self._get_response(['item3', 'item4']),
        ]
        updater = kintoupdater.Updater(
            "bucket", "collection", session=self._session)

        records, collection_data = updater.gather_remote_collection()
        assert collection_data == expected_collection_data
        assert records == ['item1', 'item2', 'item3', 'item4']


class HashComputingTest(unittest.TestCase):
    def test_records_are_not_altered(self):
        records = [
            {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
            {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
        ]
        kintoupdater.compute_hash(records)
        assert records == [
            {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
            {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
        ]

    def test_order_doesnt_matters(self):
        hash1 = kintoupdater.compute_hash([
            {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
            {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
        ])
        hash2 = kintoupdater.compute_hash([
            {'last_modified': '45678', 'id': '2', 'bar': 'baz'},
            {'foo': 'bar', 'id': '1', 'last_modified': '12345'},
        ])

        assert hash1 == hash2
