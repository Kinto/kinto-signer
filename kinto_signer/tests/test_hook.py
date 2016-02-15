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

    def test_port_is_conserved(self):
        conn_str = "https://kinto.notmyidea.org:5000/v1"
        settings = hook.get_server_settings(conn_str)
        assert settings['server_url'] == 'https://kinto.notmyidea.org:5000/v1'


class ParseResourcesTest(unittest.TestCase):

    def test_missing_semicolumn_raises_an_exception(self):
        raw_resources = """
        foo
        bar
        """
        with pytest.raises(ValueError) as excinfo:
            hook.parse_resources(raw_resources, {})
        msg = "'local:bucket/coll;remote:bucket/coll'"
        assert msg in excinfo.value.message

    def test_non_local_first_argument_raises_an_exception(self):
        raw_resources = """
        foo;bar
        bar;baz
        """
        with pytest.raises(ValueError) as excinfo:
            hook.parse_resources(raw_resources, {})
        msg = "They should start with 'local:'. Got 'foo'"
        assert msg in excinfo.value.message

    def test_malformed_local_origin_raises_an_exception(self):
        raw_resources = """
        local:origin;local:destination
        """
        with pytest.raises(ValueError) as excinfo:
            hook.parse_resources(raw_resources, {})
        msg = "Resources should be defined as bucket/collection. Got 'origin'"
        assert msg in excinfo.value.message

    def test_malformed_remote_origin_raises_an_exception(self):
        raw_resources = """
        local:bucket/collection;local:destination
        """
        with pytest.raises(ValueError) as excinfo:
            hook.parse_resources(raw_resources, {})
        msg = ("Resources should be defined as bucket/collection. "
               "Got 'destination'")
        assert msg in excinfo.value.message

    def test_missing_remote_alias_raises_an_exception(self):
        raw_resources = """
        local:bucket/collection;remote:bucket/destination
        """
        with pytest.raises(ValueError) as excinfo:
            hook.parse_resources(raw_resources, {})
        msg = ("The remote alias you specified is not defined. "
               "Check for kinto_signer.")
        assert msg in excinfo.value.message

    def test_remote_alias_is_substituted_if_present(self):
        raw_resources = """
        local:bucket/collection;remote:bucket/destination
        """
        settings = {"kinto_signer.remote": "https://notmyidea.org/v1"}
        resources = hook.parse_resources(raw_resources, settings)
        resource = resources['bucket/collection']
        resource['remote']['server_url'] == "https://notmyidea.org/v1"

    def test_returned_resources_match_the_expected_format(self):
        raw_resources = """
        local:bucket/collection;remote:bucket/destination
        """
        settings = {"kinto_signer.remote": "https://notmyidea.org/v1"}
        resources = hook.parse_resources(raw_resources, settings)
        assert resources == {
            'bucket/collection': {
                'local': {'bucket': 'bucket',
                          'collection': 'destination'},
                'remote': {'auth': None,
                           'bucket': 'bucket',
                           'collection': 'destination',
                           'server_url': 'https://notmyidea.org/v1'}}}
    def test_multiple_resources_are_supported(self):
        raw_resources = """
        local:bucket/collection;remote:bucket/destination
        local:bucket/origin;local:bucket/destination,
        """
        settings = {"kinto_signer.remote": "https://notmyidea.org/v1"}
        resources = hook.parse_resources(raw_resources, settings)
        assert len(resources) == 2
