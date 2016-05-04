import base64

import requests
import six
from requests_hawk import HawkAuth
from six.moves.urllib.parse import urljoin

from .base import SignerBase


class AutographSigner(SignerBase):

    def __init__(self, server_url, hawk_id, hawk_secret):
        self.server_url = server_url
        self.auth = HawkAuth(id=hawk_id, key=hawk_secret)

    def sign(self, payload):
        if isinstance(payload, six.text_type):  # pragma: nocover
            payload = payload.encode("utf-8")

        b64_payload = base64.b64encode(payload)
        url = urljoin(self.server_url, '/sign/data')
        resp = requests.post(url, auth=self.auth, json=[{
            "input": b64_payload.decode('utf-8'),
            "template": "content-signature",
            "hashwith": "sha384"
        }])
        resp.raise_for_status()
        signature_bundle = resp.json()[0]
        signature_bundle.setdefault('signature_encoding', 'rs_base64url')
        return signature_bundle


def load_from_settings(settings, prefix=''):
    return AutographSigner(
        server_url=settings[prefix + 'autograph.server_url'],
        hawk_id=settings[prefix + 'autograph.hawk_id'],
        hawk_secret=settings[prefix + 'autograph.hawk_secret'])
