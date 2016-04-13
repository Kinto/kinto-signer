import mock
from requests import exceptions as requests_exceptions

from . import BaseWebTest
from .support import unittest


class HelloViewTest(BaseWebTest, unittest.TestCase):

    def test_capability_is_exposed(self):
        self.maxDiff = None
        resp = self.app.get('/')
        capabilities = resp.json['capabilities']
        self.assertIn('signer', capabilities)
        expected = {
            "description": "Provide signing capabilities to the server.",
            "url": ("https://github.com/Kinto/kinto-signer#kinto-signer"),
            "resources": ["source/collection1", "source/collection2"]
        }
        self.assertEqual(expected, capabilities['signer'])


class HeartbeatTest(BaseWebTest, unittest.TestCase):

    def test_heartbeat_is_exposed(self):
        resp = self.app.get('/__heartbeat__')
        assert "signer" in resp.json

    def test_heartbeat_fails_if_unreachable(self):
        patch = mock.patch('kinto_signer.signer.autograph.requests')
        mocked = patch.start()
        self.addCleanup(patch.stop)
        mocked.post.side_effect = requests_exceptions.ConnectTimeout()
        resp = self.app.get('/__heartbeat__', status=503)
        assert resp.json["signer"] is False

    def test_heartbeat_fails_if_missing_attributes(self):
        patch = mock.patch('kinto_signer.signer.autograph.requests')
        mocked = patch.start()
        self.addCleanup(patch.stop)

        mocked.post.return_value.json.return_value = [{"signature": "bar"}]
        resp = self.app.get('/__heartbeat__', status=503)
        assert resp.json["signer"] is False
