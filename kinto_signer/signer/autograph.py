import base64
from urllib.parse import urljoin
import warnings

import requests
from requests_hawk import HawkAuth

from .base import SignerBase
from ..utils import get_first_matching_setting


class AutographSigner(SignerBase):

    def __init__(self, server_url, hawk_id, hawk_secret):
        self.server_url = server_url
        self.auth = HawkAuth(id=hawk_id, key=hawk_secret)

    def sign(self, payload):
        if isinstance(payload, str):  # pragma: nocover
            payload = payload.encode('utf-8')

        b64_payload = base64.b64encode(payload)
        url = urljoin(self.server_url, '/sign/data')
        resp = requests.post(url, auth=self.auth, json=[{
            "input": b64_payload.decode('utf-8')
        }])
        resp.raise_for_status()
        signature_bundle = resp.json()[0]
        return signature_bundle


def load_from_settings(settings, prefix='', *, prefixes=None):
    if prefixes is None:
        prefixes = [prefix]

    if prefix != '':
        message = ('signer.load_from_settings `prefix` parameter is deprecated, please '
                   'use `prefixes` instead.')
        warnings.warn(message, DeprecationWarning)

    return AutographSigner(
        server_url=get_first_matching_setting('autograph.server_url', settings, prefixes),
        hawk_id=get_first_matching_setting('autograph.hawk_id', settings, prefixes),
        hawk_secret=get_first_matching_setting('autograph.hawk_secret', settings, prefixes))
