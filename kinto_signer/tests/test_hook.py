import mock
import pytest
from .support import unittest

from kinto_signer import hook


class GetServerSettingsTest(unittest.TestCase):

    def setUp(self):
        self.connection_string = "https://alex:pass@kinto.notmyidea.org/v1"

    def test_auth_is_parsed(self):

        settings = hook.get_server_settings(self.connection_string)
        assert settings['auth'] == ('alex', 'pass')

    def test_auth_is_removed_from_server_url(self):
        settings = hook.get_server_settings(self.connection_string)
        assert settings['server_url'] == "https://kinto.notmyidea.org/v1"

    def test_local_connection_string_is_kept_intact(self):
        settings = hook.get_server_settings("local")
        assert settings['server_url'] == 'local'

    def test_auth_is_preserved_if_passed_as_argument(self):
        settings = hook.get_server_settings(
            self.connection_string,
            auth=mock.sentinel.auth
        )
        assert settings['auth'] == mock.sentinel.auth

    def test_exception_is_raised_if_url_is_incorrect(self):
        with pytest.raises(ValueError) as excinfo:
            hook.get_server_settings("https://notmyidea.org")
        assert "Please specify" in excinfo.value.message
        assert "got https://notmyidea.org" in excinfo.value.message

    def test_extra_kwargs_are_returned(self):
        settings = hook.get_server_settings(
            self.connection_string,
            foo=mock.sentinel.bar
        )
        assert settings['foo'] == mock.sentinel.bar
