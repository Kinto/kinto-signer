import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec


class SignerBackend(object):
    padding = False

    def __init__(self, settings=None):
        self.settings = settings or {}

    def export_private_key_as_pem(self, key):
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
        return pem

    def export_public_key_as_pem(self, key):
        return key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def load_private_key(self):
        # Check settings validity
        if 'private_key' not in self.settings:
            msg = 'Please, specify the private_key location in the settings.'
            raise ValueError(msg)
        with open(self.settings['private_key'], 'rb') as key_file:
            return serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend())

    def sign(self, payload):
        private_key = self.load_private_key()

        signer = private_key.signer(*self.get_signer_args())

        signer.update(payload)
        signature = signer.finalize()
        return base64.b64encode(signature)

    def verify(self, payload, signature):
        signature_bytes = base64.b64decode(signature)
        public_key = self.load_private_key().public_key()
        verifier = public_key.verifier(
            signature_bytes,
            *self.get_signer_args())
        verifier.update(payload)
        verifier.verify()


class RSABackend(SignerBackend):
    """Local RSA signature backend.
    """
    key_size = 4096

    def _get_padding(self):
        return padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH)

    def get_signer_args(self):
        return [self._get_padding(), hashes.SHA256()]

    def generate_keypair(self):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
            backend=default_backend())
        return (
            self.export_private_key_as_pem(private_key),
            self.export_public_key_as_pem(private_key.public_key())
        )


class ECDSABackend(SignerBackend):
    """Local ECDSA signature backend.
    """

    def get_signer_args(self):
        return [ec.ECDSA(hashes.SHA256())]

    def generate_keypair(self):
        private_key = ec.generate_private_key(
            ec.SECP384R1(), default_backend()
        )
        return (
            self.export_private_key_as_pem(private_key),
            self.export_public_key_as_pem(private_key.public_key())
        )
