import tempfile
import re

import pytest
from cryptography.exceptions import InvalidSignature

from kintoupdater import signing
from .support import unittest


class RSABackendTest(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        backend = signing.RSABackend()
        key = backend.generate_key()
        tmp = tempfile.mktemp('key')
        with open(tmp, 'wc') as tmp_file:
            tmp_file.write(key)
        self.key_location = tmp
        self.signer = signing.RSABackend(
            {'private_key': self.key_location}
        )

    def test_keyloading_fails_if_no_settings(self):
        backend = signing.RSABackend()
        with pytest.raises(ValueError) as e:
            backend.load_private_key()

    def test_key_loading_works(self):
        key = self.signer.load_private_key()
        assert key is not None

    def test_signing_roundtrip(self):
        signature = self.signer.sign("this is some text")
        self.signer.verify("this is some text", signature)

    def test_wrong_signature_raises_an_error(self):
        with pytest.raises(InvalidSignature):
            self.signer.verify("this is some text", "wrong sig")

    def test_signing_returns_a_hexadecimal_string(self):
        signature = self.signer.sign("this is some text")
        assert re.match(
            r'(?:[A-Za-z0-9+/]{4}){2,}(?:[A-Za-z0-9+/]{2}[AEIMQUYcgkosw048]' +
             '=|[A-Za-z0-9+/][AQgw]==)', signature) is not None
