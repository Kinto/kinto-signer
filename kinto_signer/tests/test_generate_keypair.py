import tempfile

from .support import unittest

from kinto_signer.signer import ECDSABackend
from kinto_signer import generate_keypair


class KeyPairGeneratorTest(unittest.TestCase):

    def test_generated_keypairs_can_be_loaded(self):
        private_key_location = tempfile.mktemp('private_key')
        public_key_location = tempfile.mktemp('public_key')

        generate_keypair(private_key_location, public_key_location)
        backend = ECDSABackend(settings={})
