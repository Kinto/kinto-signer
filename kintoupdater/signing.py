from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class RSABackend(object):
    """Local RSA signature backend.
    """
    def __init__(self, settings=None):
        if settings is None:
            settings = {}
        self.settings = settings

    def _get_padding(self):
        return padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH)

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

    def generate_key(self):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
            backend=default_backend())
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
        return pem

    def sign(self, payload):
        private_key = self.load_private_key()

        signer = private_key.signer(
            self._get_padding(),
            hashes.SHA256())

        signer.update(payload)
        return signer.finalize()

    def verify(self, payload, signature):
        public_key = self.load_private_key().public_key()
        verifier = public_key.verifier(
            signature,
            self._get_padding(),
            hashes.SHA256())
        verifier.update(payload)
        verifier.verify()
