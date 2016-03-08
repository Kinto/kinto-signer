from cliquet.tests.support import unittest

from . import BaseWebTest


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
