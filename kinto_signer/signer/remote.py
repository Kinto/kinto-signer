import urlparse
import requests
from requests_hawk import HawkAuth
import base64


class AutographSigner(object):

    def __init__(self, settings=None):
        hawk_id = settings['kinto_signer.autograph.hawk_id']
        hawk_secret = settings['kinto_signer.autograph.hawk_secret']
        self.server_url = settings['kinto_signer.autograph.server_url']
        self.auth = HawkAuth(id=hawk_id, key=hawk_secret)

    def sign(self, payload):
        url = urlparse.urljoin(self.server_url, '/signature')
        resp = requests.post(url, auth=self.auth, json=[{
            "input": payload
        }])
        signature = resp.json()[0]['signatures'][0]
        decoded_signature = base64.urlsafe_b64decode(
            signature['signature'].encode('utf-8'))
        return base64.b64encode(decoded_signature)
