import mock
import pytest
from pyramid import testing
from pyramid.exceptions import ConfigurationError
from requests import exceptions as requests_exceptions

from kinto_signer import on_collection_changed
from kinto_signer import includeme
from kinto_signer import utils

from . import BaseWebTest
from .support import unittest


class HelloViewTest(BaseWebTest, unittest.TestCase):

    def test_capability_is_exposed(self):
        self.maxDiff = None
        resp = self.app.get('/')
        capabilities = resp.json['capabilities']
        self.assertIn('signer', capabilities)
        expected = {
            "description": "Digital signatures for integrity and authenticity of records.",  # NOQA
            "url": ("https://github.com/Kinto/kinto-signer#kinto-signer"),
            "resources": [
                {"destination": {"bucket": "destination",
                                 "collection": "collection1"},
                 "source": {"bucket": "source",
                            "collection": "collection1"}},
                {"destination": {"bucket": "destination",
                                 "collection": "collection2"},
                 "source": {"bucket": "source",
                            "collection": "collection2"}}]
        }
        self.assertEqual(expected, capabilities['signer'])


class HeartbeatTest(BaseWebTest, unittest.TestCase):

    def setUp(self):
        patch = mock.patch('kinto_signer.signer.autograph.requests')
        self.mock = patch.start()
        self.addCleanup(patch.stop)
        self.signature = {"signature": "",
                          "hash_algorithm": "",
                          "signature_encoding": "",
                          "content-signature": "",
                          "x5u": ""}
        self.mock.post.return_value.json.return_value = [self.signature]

    def test_heartbeat_is_exposed(self):
        resp = self.app.get('/__heartbeat__')
        assert "signer" in resp.json

    def test_heartbeat_fails_if_unreachable(self):
        self.mock.post.side_effect = requests_exceptions.ConnectTimeout()
        resp = self.app.get('/__heartbeat__', status=503)
        assert resp.json["signer"] is False

    def test_heartbeat_fails_if_missing_attributes(self):
        invalid = self.signature.copy()
        invalid.pop('signature')
        self.mock.post.return_value.json.return_value = [invalid]
        resp = self.app.get('/__heartbeat__', status=503)
        assert resp.json["signer"] is False


class IncludeMeTest(unittest.TestCase):
    def test_includeme_raises_value_error_if_no_resource_defined(self):
        config = testing.setUp(settings={'signer.ecdsa.private_key': "",
                                         'signer.ecdsa.public_key': ""})
        config.registry.heartbeats = {}
        with pytest.raises(ConfigurationError):
            includeme(config)


class ResourceChangedTest(unittest.TestCase):

    def setUp(self):
        patch = mock.patch('kinto_signer.LocalUpdater')
        self.updater_mocked = patch.start()
        self.addCleanup(patch.stop)

    def test_nothing_happens_when_resource_is_not_configured(self):
        evt = mock.MagicMock(payload={"bucket_id": "a", "collection_id": "b"})
        on_collection_changed(evt, resources=utils.parse_resources("c/d;e/f"))
        assert not self.updater_mocked.called

    def test_nothing_happens_when_status_is_not_to_sign(self):
        evt = mock.MagicMock(payload={"bucket_id": "a", "collection_id": "b"},
                             impacted_records=[{"new": {"status": "signed"}}])
        on_collection_changed(evt, resources=utils.parse_resources("a/b;c/d"))
        assert not self.updater_mocked.called

    def test_updater_is_called_when_resource_and_status_matches(self):
        evt = mock.MagicMock(payload={"bucket_id": "a", "collection_id": "b"},
                             impacted_records=[{"new": {"status": "to-sign"}}])
        evt.request.registry.storage = mock.sentinel.storage
        evt.request.registry.permission = mock.sentinel.permission
        evt.request.registry.signer = mock.sentinel.signer
        on_collection_changed(evt, resources=utils.parse_resources("a/b;c/d"))
        self.updater_mocked.assert_called_with(
            signer=mock.sentinel.signer,
            storage=mock.sentinel.storage,
            permission=mock.sentinel.permission,
            source={"bucket": "a", "collection": "b"},
            destination={"bucket": "c", "collection": "d"})

        assert self.updater_mocked.return_value.sign_and_update_remote.called
