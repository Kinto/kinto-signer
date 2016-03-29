import pytest
from .support import unittest

from kinto_signer import utils


class ParseResourcesTest(unittest.TestCase):

    def test_missing_semicolumn_raises_an_exception(self):
        raw_resources = """
        foo
        bar
        """
        with pytest.raises(ValueError) as excinfo:
            utils.parse_resources(raw_resources)
        msg = "'bucket/coll;bucket/coll'"
        assert msg in str(excinfo.value)

    def test_non_local_first_argument_raises_an_exception(self):
        raw_resources = """
        foo;bar
        bar;baz
        """
        with pytest.raises(ValueError) as excinfo:
            utils.parse_resources(raw_resources)
        msg = "Resources should be defined as bucket/collection."
        assert msg in str(excinfo.value)

    def test_returned_resources_match_the_expected_format(self):
        raw_resources = """
        sourcebucket/sourcecoll;destinationbucket/destinationcoll
        """
        resources = utils.parse_resources(raw_resources)
        assert resources == {
            'sourcebucket/sourcecoll': {
                'source': {
                    'bucket': 'sourcebucket',
                    'collection': 'sourcecoll'
                },
                'destination': {
                    'bucket': 'destinationbucket',
                    'collection': 'destinationcoll'
                }
            }
        }

    def test_multiple_resources_are_supported(self):
        raw_resources = """
        origin/coll1;dest/coll1
        origin/coll2;dest/coll2
        """
        resources = utils.parse_resources(raw_resources)
        assert len(resources) == 2


class GetSettingTest(unittest.TestCase):

    def test_system_wide_settings_are_returned_if_no_resource_specified(self):
        assert 42 == utils.get_setting(settings={'signer.foo': 42}, key='foo')

    def test_resource_specific_settings_are_returned_if_only_option(self):
        retrieved = utils.get_setting(
            settings={'signer.buck_coll.foo': 42},
            key='foo',
            bucket='buck',
            collection='coll')
        assert retrieved == 42

    def test_resource_specific_settings_are_returned_if_many_options(self):
        retrieved = utils.get_setting(
            settings={
                'signer.buck_coll.foo': 42,
                'signer.foo': -1},
            key='foo',
            bucket='buck',
            collection='coll')
        assert retrieved == 42

    def test_system_wide_settings_are_returned_if_only_option(self):
        retrieved = utils.get_setting(
            settings={'signer.foo': 42},
            key='foo',
            bucket='buck',
            collection='coll')
        assert retrieved == 42

    def test_default_value_are_returned_as_fallback(self):
        retrieved = utils.get_setting(
            settings={},
            key='foo',
            bucket='buck',
            collection='coll',
            default=42)
        assert retrieved == 42

    def test_none_is_returned_in_case_no_key_matches(self):
        retrieved = utils.get_setting(
            settings={},
            key='foo',
            bucket='buck',
            collection='coll')
        assert retrieved is None
