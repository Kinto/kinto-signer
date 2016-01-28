import tempfile
import re
import os

import pytest
from cryptography.exceptions import InvalidSignature

from kinto_updater import signer
from .support import unittest


class BackendTestBase(object):

    @classmethod
    def get_backend(cls, options=None):
        return cls.backend_class(options)

    @classmethod
    def setUpClass(cls):
        backend = cls.get_backend()
        key, _ = backend.generate_keypair()
        tmp = tempfile.mktemp('key')
        with open(tmp, 'wc') as tmp_file:
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

    def test_signer_returns_a_hexadecimal_string(self):
        signature = self.signer.sign("this is some text")
        hexa_regexp = (r'(?:[A-Za-z0-9+/]{4}){2,}(?:[A-Za-z0-9+/]'
                       '{2}[AEIMQUYcgkosw048]=|[A-Za-z0-9+/][AQgw]==)')
        assert re.match(hexa_regexp, signature) is not None

    def test_load_private_key_raises_if_no_key_specified(self):
        with pytest.raises(ValueError):
            self.get_backend().load_private_key()


class RSABackendTest(BackendTestBase, unittest.TestCase):
    backend_class = signer.RSABackend


class ECDSABackendTest(BackendTestBase, unittest.TestCase):
    backend_class = signer.ECDSABackend
