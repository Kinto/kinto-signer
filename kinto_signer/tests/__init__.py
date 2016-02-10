import os

import webtest
from cliquet import utils as cliquet_utils
from cliquet.tests import support as cliquet_support


def get_user_headers(user):
    credentials = "%s:secret" % user
    authorization = 'Basic {0}'.format(cliquet_utils.encode64(credentials))
    return {
        'Authorization': authorization
    }


class BaseWebTest(object):
    config = 'config/signer.ini'

    def __init__(self, *args, **kwargs):
        super(BaseWebTest, self).__init__(*args, **kwargs)
        self.app = self.make_app()

    def make_app(self):
        curdir = os.path.dirname(os.path.realpath(__file__))
        app = webtest.TestApp("config:%s" % self.config, relative_to=curdir)
        app.RequestClass = cliquet_support.get_request_class(prefix="v1")
        return app
