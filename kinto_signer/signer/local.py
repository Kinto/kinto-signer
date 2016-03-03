import base64
import six

import ecdsa
from ecdsa import NIST384p, SigningKey, VerifyingKey
import hashlib

from .exceptions import BadSignatureError


class ECDSASigner(object):

    def __init__(self, settings=None):
        self.settings = settings or {}

    def generate_keypair(self):
        sk = SigningKey.generate(curve=NIST384p)
        vk = sk.get_verifying_key()
        return sk.to_pem(), vk.to_pem()

    def load_private_key(self):
        # Check settings validity
        if 'private_key' not in self.settings:
            msg = 'Please, specify the private_key location in the settings.'
            raise ValueError(msg)

        with open(self.settings['private_key'], 'rb') as key_file:
            return SigningKey.from_pem(key_file.read())

    def load_public_key(self):
        # Check settings validity
        if 'private_key' in self.settings:
            private_key = self.load_private_key()
            return private_key.get_verifying_key()
        elif 'public_key' in self.settings:
            with open(self.settings['public_key'], 'rb') as key_file:
                return VerifyingKey.from_pem(key_file.read())
        else:
            msg = ("Please, specify the private_key or public_key location in "
                   "the settings")
            raise ValueError(msg)

    def sign(self, payload):
        if isinstance(payload, six.text_type):  # pragma: nocover
            payload = payload.encode('utf-8')

        private_key = self.load_private_key()
        signature = private_key.sign(
            payload,
            hashfunc=hashlib.sha384,
            sigencode=ecdsa.util.sigencode_string)
        return base64.b64encode(signature).decode('utf-8')

    def verify(self, payload, signature):
        if isinstance(payload, six.text_type):  # pragma: nocover
            payload = payload.encode('utf-8')

        if isinstance(signature, six.text_type):  # pragma: nocover
            signature = signature.encode('utf-8')

        signature_bytes = base64.b64decode(signature)

        public_key = self.load_public_key()
        try:
            public_key.verify(
                signature_bytes,
                payload,
                hashfunc=hashlib.sha384,
                sigdecode=ecdsa.util.sigdecode_string)
        except Exception as e:
            raise BadSignatureError(e)
