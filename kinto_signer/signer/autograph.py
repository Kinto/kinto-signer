import requests
from requests_hawk import HawkAuth
import base64

from six.moves.urllib.parse import urljoin


class AutographSigner(object):

    def __init__(self, server_url, hawk_id, hawk_secret):
        self.server_url = server_url
        self.auth = HawkAuth(id=hawk_id, key=hawk_secret)

    def sign(self, payload):
        b64_payload = base64.b64encode(payload.encode('utf-8'))
        url = urljoin(self.server_url, '/sign/data')
        resp = requests.post(url, auth=self.auth, json=[{
            "input": b64_payload.decode('utf-8'),
            "hashwith": "sha384"
        }])
        resp.raise_for_status()
        signature_bundle = resp.json()[0]
        signature_bundle.setdefault('signature_encoding', 'rs_base64url')
        return signature_bundle


def load_from_settings(settings):
    return AutographSigner(
        server_url=settings['signer.autograph.server_url'],
        hawk_id=settings['signer.autograph.hawk_id'],
        hawk_secret=settings['signer.autograph.hawk_secret'])
