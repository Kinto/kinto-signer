from .support import unittest

import kintoupdater
import kintoclient
import mock
import pytest


class UpdaterConstructorTest(unittest.TestCase):
    @mock.patch('kintoupdater.kintoclient.create_session')
    def test_session_is_defined_if_not_passed(self, create_session):
        kintoupdater.Updater(
            'bucket', 'collection',
            auth=('user', 'pass'),
            signer=mock.MagicMock())

        create_session.assert_called_with(kintoclient.DEFAULT_SERVER_URL,
                                          ('user', 'pass'))

    def test_session_is_used_if_passed(self):
        updater = kintoupdater.Updater(
            'bucket', 'collection',
            session=mock.sentinel.session,
            signer=mock.MagicMock())
        assert updater.session == mock.sentinel.session

    def test_error_is_raised_on_missing_args(self):
        with pytest.raises(ValueError) as e:
            kintoupdater.Updater('bucket', 'collection')
        assert 'session or auth should be defined' in e.value

    @mock.patch('kintoupdater.Endpoints')
    def test_endpoints_is_created_by_constructor(self, endpoints):
        kintoupdater.Updater('bucket', 'collection',
                             auth=('user', 'pass'),
                             signer=mock.MagicMock())
        endpoints.assert_called_with()

    def test_endpoints_is_used_if_passed(self):
        updater = kintoupdater.Updater('bucket', 'collection',
                                       auth=('user', 'pass'),
                                       signer=mock.MagicMock(),
                                       endpoints=mock.sentinel.endpoints)
        assert updater.endpoints == mock.sentinel.endpoints


class UpdaterGatherRemoteCollectionTest(unittest.TestCase):

    def setUp(self):
        self._session = mock.MagicMock()

    def _build_response(self, data, headers=None):
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
            self._build_response(expected_collection_data),
            # Second one returns a list of items with a pagination token.
            self._build_response(
                [{'id': '1', 'value': 'item1'},
                {'id': '2', 'value': 'item2'},],
                {'Next-Page': 'token'}),
            # Third one returns a list of items without a pagination token.
            self._build_response(
                [{'id': '3', 'value': 'item3'},
                {'id': '4', 'value': 'item4'},],
            ),
        ]
        updater = kintoupdater.Updater(
            'bucket', 'collection', session=self._session,
            signer=mock.MagicMock())

        records, collection_data = updater.gather_remote_collection()
        assert collection_data == expected_collection_data
        assert records == {
            '1': {'id': '1', 'value': 'item1'},
            '2': {'id': '2', 'value': 'item2'},
            '3': {'id': '3', 'value': 'item3'},
            '4': {'id': '4', 'value': 'item4'},
        }


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


class BatchRequestsTest(unittest.TestCase):
    def setUp(self):
        self.session = mock.MagicMock()
        self.endpoints = mock.MagicMock()

    def test_requests_are_stacked(self):
        batch = kintoupdater.Batch(self.session, self.endpoints)
        batch.add('GET', '/foobar/baz',
                  mock.sentinel.data,
                  mock.sentinel.permissions)
        assert len(batch.requests) == 1

    def test_send_adds_data_attribute(self):
        batch = kintoupdater.Batch(self.session, self.endpoints)
        batch.add('GET', '/foobar/baz', data={'foo': 'bar'})
        batch.send()

        self.session.request.assert_called_with(
            'POST',
            self.endpoints.batch(),
            data={'requests': [{
                'method': 'GET',
                'path': '/foobar/baz',
                'body': {'data': {'foo': 'bar'}}
            }]}
        )

    def test_send_adds_permissions_attribute(self):
        batch = kintoupdater.Batch(self.session, self.endpoints)
        batch.add('GET', '/foobar/baz', permissions=mock.sentinel.permissions)
        batch.send()

        self.session.request.assert_called_with(
            'POST',
            self.endpoints.batch(),
            data={'requests': [{
                'method': 'GET',
                'path': '/foobar/baz',
                'body': {'permissions': mock.sentinel.permissions}
            }]}
        )

    def test_send_empties_the_requests_cache(self):
        batch = kintoupdater.Batch(self.session, self.endpoints)
        batch.add('GET', '/foobar/baz', permissions=mock.sentinel.permissions)
        assert len(batch.requests) == 1
        batch.send()
        assert len(batch.requests) == 0

    def test_context_manager_works_as_expected(self):
        with kintoupdater.batch_requests(self.session, self.endpoints) as batch:
            batch.add('PUT', '/records/1234', data={'foo': 'bar'})
            batch.add('PUT', '/records/5678', data={'bar': 'baz'})

        assert self.session.request.called


class DataValidityTest(unittest.TestCase):

    def setUp(self):
        self.session = mock.MagicMock()
        self.endpoints = mock.MagicMock()
        self.signer = mock.MagicMock()

    def test_data_validity_uses_configured_backend(self):
        updater = kintoupdater.Updater(
            'bucket', 'collection',
            auth=('user', 'pass'),
            session=self.session,
            endpoints=self.endpoints,
            signer=self.signer
        )
        updater.compute_hash = mock.MagicMock(return_value='1234')

        records = [{'id': '1', 'data': 'value'}]
        updater.check_data_validity(records, mock.sentinel.signature)
        self.signer.verify.assert_called_with(
            '1234',
            mock.sentinel.signature
        )
