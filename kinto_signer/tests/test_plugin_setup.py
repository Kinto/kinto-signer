from cliquet.tests.support import unittest

from . import BaseWebTest


class HelloViewTest(BaseWebTest, unittest.TestCase):

    def test_capability_is_exposed(self):
        resp = self.app.get('/')
        capabilities = resp.json['capabilities']
        self.assertIn('signer', capabilities)
        expected = {
            "bucket": "buck",
            "collection": "coll",
            "description": "Provide signing capabilities to the "
            "/buckets/buck/collections/coll collection.",
            "url": "https://github.com/mozilla-services/kinto-signer"
            "#kinto-signer",
        }
        self.assertEqual(expected, capabilities['signer'])
