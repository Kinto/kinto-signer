import os

from kinto_signer.signer.local_ecdsa import ECDSASigner
from kinto_signer.signer.autograph import AutographSigner


autograph_signer = AutographSigner(
    server_url='http://localhost:8000',
    hawk_id='alice',
    hawk_secret='fs5wgcer9qj819kfptdlp8gm227ewxnzvsuj9ztycsx08hfhzu')

here = os.path.abspath(os.path.dirname(__file__))
config_folder = os.path.join(here, '..', 'kinto_signer', 'tests', 'config')
python_signer = ECDSASigner(
    private_key=os.path.join(config_folder, 'ecdsa.private.pem'),
    public_key=os.path.join(config_folder, 'ecdsa.public.pem'))


def sign_data(signer, data):
    signature = signer.sign(data)
    print("signature", signature)


data = "TEST"
sign_data(autograph_signer, data)
sign_data(python_signer, data)
