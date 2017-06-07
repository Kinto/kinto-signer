import unittest

import mock
import pytest
from kinto import main as kinto_main
from kinto.core.events import ResourceChanged
from pyramid import testing
from pyramid.exceptions import ConfigurationError
from requests import exceptions as requests_exceptions

from kinto_signer import __version__ as signer_version
from kinto_signer.signer.autograph import AutographSigner
from kinto_signer import includeme
from kinto_signer.listeners import sign_collection_data
from kinto_signer import utils

from .support import BaseWebTest, get_user_headers


class HelloViewTest(BaseWebTest, unittest.TestCase):

    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)
        settings['signer.alice_source.to_review_enabled'] = 'true'
        settings['signer.alice_source.reviewers_group'] = 'revoyeurs'
        return settings

    def test_capability_is_exposed(self):
        self.maxDiff = None
        resp = self.app.get('/')
        capabilities = resp.json['capabilities']
        self.assertIn('signer', capabilities)
        expected = {
            "description": "Digital signatures for integrity and authenticity of records.",  # NOQA
            "url": ("https://github.com/Kinto/kinto-signer#kinto-signer"),
            "version": signer_version,
            "to_review_enabled": False,
            "group_check_enabled": False,
            "editors_group": "editors",
            "reviewers_group": "reviewers",
            "resources": [{
                "destination": {"bucket": "alice",
                                "collection": "destination"},
                "source": {"bucket": "alice",
                           "collection": "source"},
                "reviewers_group": "revoyeurs",
                "to_review_enabled": True
            }, {
                "destination": {"bucket": "alice",
                                "collection": "to"},
                "preview": {"bucket": "alice",
                            "collection": "preview"},
                "source": {"bucket": "alice",
                           "collection": "from"}
            }, {
                "destination": {"bucket": "bob",
                                "collection": "destination"},
                "source": {"bucket": "bob",
                           "collection": "source"}
            }]
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
    def includeme(self, settings):
        config = testing.setUp(settings=settings)
        kinto_main(None, config=config)
        includeme(config)
        return config

    def test_includeme_raises_value_error_if_no_resource_defined(self):
        with pytest.raises(ConfigurationError):
            self.includeme(settings={"signer.ecdsa.private_key": "",
                                     "signer.ecdsa.public_key": ""})

    def test_defines_a_signer_per_bucket(self):
        settings = {
            "signer.resources": (
                "/buckets/sb1/collections/sc1;/buckets/db1/collections/dc1\n"
            ),
            "signer.sb1.signer_backend": "kinto_signer.signer.local_ecdsa",
            "signer.sb1.ecdsa.public_key": "/path/to/key",
            "signer.sb1.ecdsa.private_key": "/path/to/private",
        }
        config = self.includeme(settings)
        signer, = config.registry.signers.values()
        assert signer.public_key == "/path/to/key"

    def test_defines_a_signer_per_bucket_and_collection(self):
        settings = {
            "signer.resources": (
                "/buckets/sb1/collections/sc1;/buckets/db1/collections/dc1\n"
                "/buckets/sb1/collections/sc2;/buckets/db1/collections/dc2"
            ),
            "signer.sb1.signer_backend": "kinto_signer.signer.local_ecdsa",
            "signer.sb1.ecdsa.public_key": "/path/to/key",
            "signer.sb1.ecdsa.private_key": "/path/to/private",
            "signer.sb1_sc1.signer_backend": "kinto_signer.signer.autograph",
            "signer.sb1_sc1.autograph.server_url": "http://localhost",
            "signer.sb1_sc1.autograph.hawk_id": "alice",
            "signer.sb1_sc1.autograph.hawk_secret": "a-secret",
        }
        config = self.includeme(settings)
        signer1, signer2 = config.registry.signers.values()
        if isinstance(signer1, AutographSigner):
            signer1, signer2 = signer2, signer1
        assert signer1.public_key == "/path/to/key"
        assert signer2.server_url == "http://localhost"

    def test_a_statsd_timer_is_used_for_signature_if_configured(self):
        settings = {
            "statsd_url": "udp://127.0.0.1:8125",
            "signer.resources": (
                "/buckets/sb1/collections/sc1;/buckets/db1/collections/dc1"
            ),
            "signer.ecdsa.public_key": "/path/to/key",
            "signer.ecdsa.private_key": "/path/to/private",
        }
        config = self.includeme(settings)

        payload = dict(resource_name='collection',
                       action='update',
                       bucket_id='foo')
        event = ResourceChanged(payload=payload,
                                impacted_records=[],
                                request=mock.MagicMock())
        statsd_client = config.registry.statsd._client
        with mock.patch.object(statsd_client, 'timing') as mocked:
            config.registry.notify(event)
            timers = set(c[0][0] for c in mocked.call_args_list)
            assert 'plugins.signer' in timers


class OnCollectionChangedTest(unittest.TestCase):

    def setUp(self):
        patch = mock.patch('kinto_signer.listeners.LocalUpdater')
        self.updater_mocked = patch.start()
        self.addCleanup(patch.stop)

    def test_nothing_happens_when_resource_is_not_configured(self):
        evt = mock.MagicMock(payload={"bucket_id": "a", "collection_id": "b"})
        sign_collection_data(evt, resources=utils.parse_resources("c/d;e/f"))
        assert not self.updater_mocked.called

    def test_nothing_happens_when_status_is_not_to_sign(self):
        evt = mock.MagicMock(payload={"bucket_id": "a", "collection_id": "b"},
                             impacted_records=[{
                                 "new": {"id": "b", "status": "signed"}}])
        sign_collection_data(evt, resources=utils.parse_resources("a/b;c/d"))
        assert not self.updater_mocked.sign_and_update_destination.called

    def test_updater_is_called_when_resource_and_status_matches(self):
        evt = mock.MagicMock(payload={"bucket_id": "a", "collection_id": "b"},
                             impacted_records=[{
                                 "new": {"id": "b", "status": "to-sign"}}])
        evt.request.registry.storage = mock.sentinel.storage
        evt.request.registry.permission = mock.sentinel.permission
        evt.request.registry.signers = {
            "/buckets/a/collections/b": mock.sentinel.signer
        }
        evt.request.route_path.return_value = "/v1/buckets/a/collections/b"
        sign_collection_data(evt, resources=utils.parse_resources("a/b;c/d"))
        self.updater_mocked.assert_called_with(
            signer=mock.sentinel.signer,
            storage=mock.sentinel.storage,
            permission=mock.sentinel.permission,
            source={"bucket": "a", "collection": "b"},
            destination={"bucket": "c", "collection": "d"})

        mocked = self.updater_mocked.return_value
        assert mocked.sign_and_update_destination.called

    def test_updater_does_not_fail_when_payload_is_inconsistent(self):
        # This happens with events on default bucket for kinto < 3.3
        evt = mock.MagicMock(payload={"subpath": "collections/boom"})
        sign_collection_data(evt, resources=utils.parse_resources("a/b;c/d"))


class BatchTest(BaseWebTest, unittest.TestCase):
    def setUp(self):
        super(BatchTest, self).setUp()
        self.headers = get_user_headers('me')
        self.app.put_json("/buckets/alice", headers=self.headers)
        self.app.put_json("/buckets/bob", headers=self.headers)

        # Patch calls to Autograph.
        patch = mock.patch('kinto_signer.signer.autograph.requests')
        self.mock = patch.start()
        self.addCleanup(patch.stop)
        self.mock.post.return_value.json.return_value = [{
            "signature": "",
            "hash_algorithm": "",
            "signature_encoding": "",
            "content-signature": "",
            "x5u": ""}]

    def test_various_collections_can_be_signed_using_batch(self):
        self.app.put_json("/buckets/alice/collections/source",
                          headers=self.headers)
        self.app.put_json("/buckets/bob/collections/source",
                          headers=self.headers)

        self.app.post_json("/batch", {
            "defaults": {
                "method": "PATCH",
                "body": {"data": {"status": "to-sign"}}
            },
            "requests": [
                {"path": "/buckets/alice/collections/source"},
                {"path": "/buckets/bob/collections/source"},
            ]
        }, headers=self.headers)

        resp = self.app.get("/buckets/alice/collections/source",
                            headers=self.headers)
        assert resp.json["data"]["status"] == "signed"
        resp = self.app.get("/buckets/bob/collections/source",
                            headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_various_collections_can_be_signed_using_batch_creation(self):
        self.app.post_json("/batch", {
            "defaults": {
                "method": "POST",
                "path": "/buckets/alice/collections"
            },
            "requests": [
                {"body": {"data": {"id": "source", "status": "to-sign"}}},
                {"body": {"data": {"id": "ignored", "status": "to-sign"}}},
                {"body": {"data": {"id": "from", "status": "to-sign"}}}
            ]
        }, headers=self.headers)

        resp = self.app.get("/buckets/alice/collections/source",
                            headers=self.headers)
        assert resp.json["data"]["status"] == "signed"
        resp = self.app.get("/buckets/alice/collections/from",
                            headers=self.headers)
        assert resp.json["data"]["status"] == "signed"


class SigningErrorTest(BaseWebTest, unittest.TestCase):
    def test_returns_503_if_autograph_cannot_be_reached(self):
        headers = get_user_headers('me')
        self.app.put_json("/buckets/alice", headers=headers)
        self.app.put_json("/buckets/alice/collections/source",
                          headers=headers)
        self.app.post_json("/buckets/alice/collections/source/records",
                           {"data": {"title": "hello"}},
                           headers=headers)

        rc = '/buckets/alice/collections/source'
        self.app.app.registry.signers[rc].server_url = 'http://0.0.0.0:1234'

        self.app.patch_json("/buckets/alice/collections/source",
                            {"data": {"status": "to-sign"}},
                            headers=headers,
                            status=503)
