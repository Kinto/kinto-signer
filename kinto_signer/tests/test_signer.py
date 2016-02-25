import tempfile
import re
import os

import mock
import pytest
from cryptography.exceptions import InvalidSignature

from kinto_signer.signer.local import RSASigner, ECDSASigner
from kinto_signer.signer.remote import AutographSigner
from .support import unittest


SIGNATURE = ("MS8ZXMzr9YVttwuHgZ_SxlPogZKm_mYO6SsEiqupBeu01ELO_xP6huN4bXBn-ZH"
             "1ZJkbgBeVQ_QKd8wW9_ggJxDaPpQ3COFcpW_SdHaiEOLBcKt_SrKmLVIWHE3wc3"
             "lV")


class BackendTestBase(object):

    @classmethod
    def get_backend(cls, options=None):
        return cls.backend_class(options)

    @classmethod
    def setUpClass(cls):
        backend = cls.get_backend()
        key, _ = backend.generate_keypair()
        tmp = tempfile.mktemp('key')
        with open(tmp, 'wb+') as tmp_file:
            tmp_file.write(key)
        cls.key_location = tmp
        cls.signer = cls.get_backend(
            {'private_key': cls.key_location}
        )

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.key_location)

    def test_keyloading_fails_if_no_settings(self):
        backend = self.get_backend()
        with pytest.raises(ValueError):
            backend.load_private_key()

    def test_key_loading_works(self):
        key = self.signer.load_private_key()
        assert key is not None

    def test_signer_roundtrip(self):
        signature = self.signer.sign("this is some text")
        self.signer.verify("this is some text", signature)

    def test_wrong_signature_raises_an_error(self):
        with pytest.raises(InvalidSignature):
            self.signer.verify("this is some text", "wrong sig")

    def test_signer_returns_a_base64_string(self):
        signature = self.signer.sign("this is some text")
        hexa_regexp = (
            r'^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}'
            '==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})$')
        assert re.match(hexa_regexp, signature.decode('utf-8')) is not None

    def test_load_private_key_raises_if_no_key_specified(self):
        with pytest.raises(ValueError):
            self.get_backend().load_private_key()


class RSASignerTest(BackendTestBase, unittest.TestCase):
    backend_class = RSASigner


class ECDSASignerTest(BackendTestBase, unittest.TestCase):
    backend_class = ECDSASigner


class AutographSignerTest(unittest.TestCase):

    def setUp(self):
        settings = {
            'kinto_signer.autograph.hawk_id': 'alice',
            'kinto_signer.autograph.hawk_secret':
                'fs5wgcer9qj819kfptdlp8gm227ewxnzvsuj9ztycsx08hfhzu',
            'kinto_signer.autograph.server_url': 'http://localhost:8000'
        }
        self.signer = AutographSigner(settings)

    @mock.patch('kinto_signer.signer.remote.requests')
    def test_request_is_being_crafted_with_payload_as_input(self, requests):
        response = mock.MagicMock()
        response.json.return_value = [{"signature": SIGNATURE}]
        requests.post.return_value = response
        signed = self.signer.sign("test data")
        assert signed == ("MS8ZXMzr9YVttwuHgZ/SxlPogZKm/mYO6SsEiqupBeu01ELO"
                          "/xP6huN4bXBn+ZH1ZJkbgBeVQ/QKd8wW9/ggJxDaPpQ3COFc"
                          "pW/SdHaiEOLBcKt/SrKmLVIWHE3wc3lV")
