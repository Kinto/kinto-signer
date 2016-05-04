import base64

import ecdsa
import hashlib
import six
from ecdsa import NIST384p, SigningKey, VerifyingKey

from .base import SignerBase
from .exceptions import BadSignatureError


class ECDSASigner(SignerBase):

    def __init__(self, private_key=None, public_key=None):
        if private_key is None and public_key is None:
            msg = ("Please, specify either a private_key or public_key "
                   "location.")
            raise ValueError(msg)
        self.private_key = private_key
        self.public_key = public_key

        # Autograph uses this prefix prior to signing.
        self.prefix = "Content-Signature:\x00".encode("utf-8")

    @classmethod
    def generate_keypair(cls):
        sk = SigningKey.generate(curve=NIST384p)
        vk = sk.get_verifying_key()
        return sk.to_pem(), vk.to_pem()

    def load_private_key(self):
        if self.private_key is None:
            msg = 'Please, specify the private_key location.'
            raise ValueError(msg)

        with open(self.private_key, 'rb') as key_file:
            return SigningKey.from_pem(key_file.read())

    def load_public_key(self):
        # Check settings validity
        if self.private_key:
            private_key = self.load_private_key()
            return private_key.get_verifying_key()
        elif self.public_key:
            with open(self.public_key, 'rb') as key_file:
                return VerifyingKey.from_pem(key_file.read())

    def sign(self, payload):
        if isinstance(payload, six.text_type):  # pragma: nocover
            payload = payload.encode('utf-8')

        payload = self.prefix + payload

        private_key = self.load_private_key()
        signature = private_key.sign(payload,
                                     hashfunc=hashlib.sha384,
                                     sigencode=ecdsa.util.sigencode_string)
        x5u = ''
        enc_signature = base64.b64encode(signature).decode('utf-8')
        return {
            'signature': enc_signature,
            'hash_algorithm': 'sha384',
            'signature_encoding': 'rs_base64',
            'x5u': x5u,
            'content-signature': 'x5u=%s;p384ecdsa=%s' % (x5u, enc_signature)
        }

    def verify(self, payload, signature_bundle):
        signature = signature_bundle['signature']
        hash_algorithm = signature_bundle['hash_algorithm']
        signature_encoding = signature_bundle['signature_encoding']

        if isinstance(payload, six.text_type):  # pragma: nocover
            payload = payload.encode('utf-8')

        payload = self.prefix + payload

        if isinstance(signature, six.text_type):  # pragma: nocover
            signature = signature.encode('utf-8')

        if hash_algorithm != 'sha384':
            msg = 'Unsupported hash_algorithm: %s' % hash_algorithm
            raise ValueError(msg)
        if signature_encoding not in ('rs_base64', 'rs_base64url'):
            msg = 'Unsupported signature_encoding: %s' % signature_encoding
            raise ValueError(msg)
        if signature_encoding == 'rs_base64url':
            signature_bytes = base64.urlsafe_b64decode(signature)
        elif signature_encoding == 'rs_base64':
            signature_bytes = base64.b64decode(signature)

        public_key = self.load_public_key()
        try:
            public_key.verify(signature_bytes,
                              payload,
                              hashfunc=hashlib.sha384,
                              sigdecode=ecdsa.util.sigdecode_string)
        except Exception as e:
            raise BadSignatureError(e)


def load_from_settings(settings, prefix):
    private_key = settings.get(prefix + 'ecdsa.private_key')
    public_key = settings.get(prefix + 'ecdsa.public_key')
    try:
        return ECDSASigner(private_key=private_key, public_key=public_key)
    except ValueError:
        msg = ("Please specify either kinto.signer.ecdsa.private_key or "
               "kinto.signer.ecdsa.public_key in the settings.")
        raise ValueError(msg)
