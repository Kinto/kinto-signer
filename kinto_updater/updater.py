
import hasher
import signer
import exceptions


class Updater(object):

    def __init__(self, bucket, collection, settings=None,
                 signer_instance=None):
        if settings is None:
            settings = {}
        self.settings = settings

        if signer_instance is None:
            signer_instance = signer.RSABackend(self.settings)
        self.signer_instance = signer_instance

    def get_signature(self, records):
        new_hash = hasher.compute_hash(records.values())
        return self.signer_instance.sign(new_hash)
