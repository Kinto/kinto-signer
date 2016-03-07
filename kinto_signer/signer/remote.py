import requests
from requests_hawk import HawkAuth
import base64

from six.moves.urllib.parse import urljoin


class AutographSigner(object):

    def __init__(self, settings=None):
        hawk_id = settings['kinto_signer.autograph.hawk_id']
        hawk_secret = settings['kinto_signer.autograph.hawk_secret']
        self.server_url = settings['kinto_signer.autograph.server_url']
        self.auth = HawkAuth(id=hawk_id, key=hawk_secret)

    def sign(self, payload):
        b64_payload = base64.b64encode(payload.encode('utf-8'))
        url = urljoin(self.server_url, '/signature')
        resp = requests.post(url, auth=self.auth, json=[{
            "input": b64_payload,
            "hashwith": "sha384"
        }])
        resp.raise_for_status()
        signature = resp.json()[0]['signature'].encode('utf-8')

        # Make sure the padding is correct before decoding.
        rem = len(signature) % 4
        if rem > 0:
            signature += b'=' * (4 - rem)

        return signature.decode('utf-8')
