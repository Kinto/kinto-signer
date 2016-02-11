from .support import unittest

from kinto_signer import hook


class GetServerSettingsTest(unittest.TestCase):

    def test_auth_is_parsed(self):
        connection_string = "https://alex:pass@kinto.notmyidea.org/v1"
        settings = hook.get_server_settings(connection_string)
        assert settings['auth'] == ('alex', 'pass')

    def test_auth_is_removed_from_server_url(self):
        connection_string = "https://alex:pass@kinto.notmyidea.org/v1"
        settings = hook.get_server_settings(connection_string)
        assert settings['server_url'] == "https://kinto.notmyidea.org/v1"
