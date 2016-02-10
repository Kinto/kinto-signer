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
            "url": ("https://github.com/mozilla-services/kinto-signer"
                    "#kinto-signer"),
            "resources": ["buck/coll"]
        }
        self.assertEqual(expected, capabilities['signer'])
