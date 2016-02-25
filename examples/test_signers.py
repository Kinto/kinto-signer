from kinto_signer.signer.purepython import ECDSABackend
from kinto_signer.signer.autograph import AutographSigner

from base64 import b64decode


autograph_signer = AutographSigner({
    'kinto_signer.autograph.hawk_id': 'alice',
    'kinto_signer.autograph.hawk_secret': 'fs5wgcer9qj819kfptdlp8gm227ewxnzvsuj9ztycsx08hfhzu',
    'kinto_signer.autograph.server_url': 'http://localhost:8000'
})
python_signer = ECDSABackend({'private_key': '/home/alexis/dev/kinto-signer/kinto_signer/tests/config/ecdsa.private.pem'})


def sign_data(signer, data):
    signature = signer.sign(data)
    print("signature", signature, b64decode(signature))

data = "TEST"
sign_data(autograph_signer, data)
sign_data(python_signer, data)
