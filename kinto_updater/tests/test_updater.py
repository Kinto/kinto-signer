from collections import OrderedDict

from .support import unittest

import kinto_updater
import mock
import pytest


class BaseUpdaterTest(object):
    def _build_response(self, data, headers=None):
        if headers is None:
            headers = {}
        resp = {
            'data': data
        }
        return resp, headers


class UpdaterConstructorTest(unittest.TestCase, BaseUpdaterTest):
    @mock.patch('kinto_updater.Client')
    def test_session_is_defined_if_not_passed(self, Client):
        kinto_updater.Updater(
            'bucket', 'collection',
            server_url="http://localhost:8888/v1",
            auth=('user', 'pass'),
            signer=mock.MagicMock())

        Client.assert_called_with("http://localhost:8888/v1", None,
                                  auth=('user', 'pass'),
                                  bucket='bucket', collection='collection')

    def test_session_is_used_if_passed(self):
        updater = kinto_updater.Updater(
            'bucket', 'collection',
            session=mock.sentinel.session,
            signer=mock.MagicMock())
        assert updater.client.session == mock.sentinel.session

    def test_error_is_raised_on_missing_args(self):
        with pytest.raises(AttributeError) as e:
            kinto_updater.Updater('bucket', 'collection')
        assert 'session or auth + server_url' in e.value.message

    @mock.patch('kinto_updater.signing.RSABackend')
    def test_signer_defaults_to_rsa(self, backend):
        kinto_updater.Updater('bucket', 'collection',
                              auth=('user', 'pass'),
                              settings=mock.sentinel.settings)
        backend.assert_called_with(mock.sentinel.settings)


class UpdaterDataValidityTest(unittest.TestCase, BaseUpdaterTest):

    def setUp(self):
        self.session = mock.MagicMock()
        self.signer = mock.MagicMock()

    @mock.patch('kinto_updater.compute_hash')
    def test_data_validity_uses_configured_backend(self, compute_hash):
        updater = kinto_updater.Updater(
            'bucket', 'collection',
            auth=('user', 'pass'),
            session=self.session,
            signer=self.signer
        )
        compute_hash.return_value = '1234'

        records = {'1': {'id': '1', 'data': 'value'}}
        updater.check_data_validity(records, mock.sentinel.signature)
        self.signer.verify.assert_called_with(
            '1234',
            mock.sentinel.signature
        )


class AddRecordsTest(unittest.TestCase, BaseUpdaterTest):

    def setUp(self):
        self.signer = mock.MagicMock()
        self.updater = kinto_updater.Updater(
            'bucket', 'collection',
            server_url="http://localhost:8888/v1",
            auth=('user', 'pass'),
            signer=self.signer
        )
        self.updater.client.session = mock.MagicMock()
        self.updater.client.session.request.side_effect = [
            ({'settings': {'batch_max_requests': 25}}, {})
        ]

    def test_add_records_fails_if_existing_collection_without_signature(self):
        records = [
            {'foo': 'bar'},
            {'bar': 'baz'},
        ]
        with mock.patch.object(self.updater, 'gather_remote_collection',
                               return_value=({'1': {'foo': 'bar'}}, {})):

            with pytest.raises(kinto_updater.UpdaterException):
                self.updater.add_records(records)

    @mock.patch('uuid.uuid4')
    def test_add_records_to_empty_collection(self, uuid4):
        uuid4.side_effect = [1, 2]

        with mock.patch.object(self.updater, 'gather_remote_collection',
                               return_value=({}, {})):

            records = [
                {'foo': 'bar'},
                {'bar': 'baz'},
            ]
            self.signer.sign.return_value = '1234'

            self.updater.add_records(records)

            self.updater.client.session.request.assert_called_with(
                method='POST', endpoint='/batch', payload={'requests': [
                    {
                        'body': {'data': {'foo': 'bar', 'id': '1'}},
                        'path': ('/buckets/bucket/collections/collection'
                                 '/records/1'),
                        'method': 'PUT',
                        'headers': {'If-None-Match': '*'}
                    },
                    {
                        'body': {'data': {'bar': 'baz', 'id': '2'}},
                        'path': ('/buckets/bucket/collections/collection'
                                 '/records/2'),
                        'method': 'PUT',
                        'headers': {'If-None-Match': '*'}
                    },
                    {
                        'body': {'data': {'signature': '1234'}},
                        'path': '/buckets/bucket/collections/collection',
                        'method': 'PATCH'
                    }
                ]}
            )

    @mock.patch('kinto_updater.compute_hash')
    @mock.patch('uuid.uuid4')
    def test_add_records_to_existing_collection(self, uuid4, compute_hash):
        uuid4.side_effect = [1, 2]

        with mock.patch.object(self.updater, 'gather_remote_collection',
                               return_value=({'3': {'foo': 'bar'}},
                                             {'signature': 'sig'})):

            records = [
                {'foo': 'bar'},
                {'bar': 'baz'},
            ]
            self.signer.sign.return_value = '1234'
            compute_hash.return_value = 'hash'

            self.updater.add_records(records)

            self.signer.verify.assert_called_with('hash', 'sig')

            self.updater.client.session.request.assert_called_with(
                method='POST', endpoint='/batch', payload={'requests': [
                    {
                        'body': {'data': {'foo': 'bar', 'id': '1'}},
                        'path': ('/buckets/bucket/collections/collection'
                                 '/records/1'),
                        'method': 'PUT',
                        'headers': {'If-None-Match': '*'}
                    },
                    {
                        'body': {'data': {'bar': 'baz', 'id': '2'}},
                        'path': ('/buckets/bucket/collections/collection'
                                 '/records/2'),
                        'method': 'PUT',
                        'headers': {'If-None-Match': '*'}
                    },
                    {
                        'body': {'data': {'signature': '1234'}},
                        'path': '/buckets/bucket/collections/collection',
                        'method': 'PATCH'
                    }
                ]}
            )


class HashComputingTest(unittest.TestCase):
    def test_records_are_not_altered(self):
        records = [
            {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
            {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
        ]
        kinto_updater.compute_hash(records)
        assert records == [
            {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
            {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
        ]

    def test_order_doesnt_matters(self):
        hash1 = kinto_updater.compute_hash([
            OrderedDict({'foo': 'bar', 'last_modified': '12345', 'id': '1'}),
            OrderedDict({'bar': 'baz', 'last_modified': '45678', 'id': '2'}),
        ])
        hash2 = kinto_updater.compute_hash([
            OrderedDict({'last_modified': '45678', 'id': '2', 'bar': 'baz'}),
            OrderedDict({'foo': 'bar', 'id': '1', 'last_modified': '12345'}),
        ])

        assert hash1 == hash2
