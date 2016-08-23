import os
try:
    import ConfigParser as configparser
except ImportError:
    import configparser

from kinto import main as kinto_main

try:
    from kinto.core.testing import (
        BaseWebTest as CoreWebTest, get_user_headers, DummyRequest)
except ImportError:
    # kinto <= 4.0.0
    from kinto.tests.support import BaseWebTest as CoreWebTest, get_user_headers  # NOQA
    from kinto.tests.core.support import DummyRequest  # NOQA


here = os.path.abspath(os.path.dirname(__file__))


class BaseWebTest(CoreWebTest):
    api_prefix = "v1"
    entry_point = kinto_main
    config = 'config/signer.ini'

    def __init__(self, *args, **kwargs):
        super(BaseWebTest, self).__init__(*args, **kwargs)
        self.headers.update(get_user_headers('mat'))

    def get_app_settings(self, extras=None):
        ini_path = os.path.join(here, self.config)
        config = configparser.ConfigParser()
        config.read(ini_path)
        settings = dict(config.items('app:main'))
        settings['signer.group_check_enabled'] = False
        settings['signer.to_review_enabled'] = False
        return settings
