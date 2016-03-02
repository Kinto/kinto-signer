import tempfile
import re
import os

import mock
import pytest

from kinto_signer.signer import ECDSASigner, AutographSigner, BadSignatureError
from .support import unittest


SIGNATURE = (
    "ikfq6qOV85vR7QaNCTldVvvtcNpPIICqqMp3tfyiT7fHCgFNq410SFnIfjAPgSa"
    "jEtxxyGtZFMoI/BzO/1y5oShLtX0LH4wx/Wft7wz17T7fFqpDQ9hFZzTOPBwZUIbx")


def save_key(key, key_name):
    tmp = tempfile.mktemp(key_name)
    with open(tmp, 'wb+') as tmp_file:
        tmp_file.write(key)
    return tmp


class ECDSASignerTest(unittest.TestCase):

    @classmethod
    def get_backend(cls, options=None):
        return ECDSASigner(options)

    @classmethod
    def setUpClass(cls):
        backend = cls.get_backend()
        sk, vk = backend.generate_keypair()
        cls.sk_location = save_key(sk, 'signing-key')
        cls.vk_location = save_key(vk, 'verifying-key')

        cls.signer = cls.get_backend({
            'private_key': cls.sk_location,
        })

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.sk_location)
        os.remove(cls.vk_location)

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
        with pytest.raises(BadSignatureError):
            self.signer.verify("Text not matching with the sig.", SIGNATURE)

    def test_signer_returns_a_base64_string(self):
        signature = self.signer.sign("this is some text")
        hexa_regexp = (
            r'^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}'
            '==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})$')
        assert re.match(hexa_regexp, signature.decode('utf-8')) is not None

    def test_load_private_key_raises_if_no_key_specified(self):
        with pytest.raises(ValueError):
            self.get_backend().load_private_key()

    def test_public_key_can_be_loaded_from_public_key_pem(self):
        signer = self.get_backend({'public_key': self.vk_location})
        signer.load_public_key()

    def test_public_key_can_be_loaded_from_private_key_pem(self):
        signer = self.get_backend({'private_key': self.sk_location})
        signer.load_public_key()

    def test_load_public_key_raises_an_error_if_missing_settings(self):
        signer = self.get_backend()
        with pytest.raises(ValueError) as excinfo:
            signer.load_public_key()
        msg = ("Please, specify the private_key or public_key location in the "
               "settings")
        assert str(excinfo.value) == msg


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
        assert signed == SIGNATURE
