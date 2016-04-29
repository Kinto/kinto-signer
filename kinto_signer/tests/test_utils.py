import pytest
from .support import unittest

from kinto_signer import utils


class ParseResourcesTest(unittest.TestCase):

    def test_missing_semicolumn_raises_an_exception(self):
        raw_resources = """
        foo
        bar
        """
        with pytest.raises(ValueError):
            utils.parse_resources(raw_resources)

    def test_non_local_first_argument_raises_an_exception(self):
        raw_resources = """
        foo;bar
        bar;baz
        """
        with pytest.raises(ValueError):
            utils.parse_resources(raw_resources)

    def test_malformed_url_raises_an_exception(self):
        raw_resources = """
        /buckets/sbid/scid;/buckets/dbid/collections/dcid
        """
        with pytest.raises(ValueError):
            utils.parse_resources(raw_resources)

    def test_returned_resources_match_the_expected_format(self):
        raw_resources = """
        /buckets/sbid/collections/scid;/buckets/dbid/collections/dcid
        """
        resources = utils.parse_resources(raw_resources)
        assert resources == {
            '/buckets/sbid/collections/scid': {
                'source': {
                    'bucket': 'sbid',
                    'collection': 'scid'
                },
                'destination': {
                    'bucket': 'dbid',
                    'collection': 'dcid'
                }
            }
        }

    def test_returned_resources_match_the_legacy_format(self):
        raw_resources = """
        sbid/scid;dbid/dcid
        """
        resources = utils.parse_resources(raw_resources)
        assert resources == {
            '/buckets/sbid/collections/scid': {
                'source': {
                    'bucket': 'sbid',
                    'collection': 'scid'
                },
                'destination': {
                    'bucket': 'dbid',
                    'collection': 'dcid'
                }
            }
        }

    def test_multiple_resources_are_supported(self):
        raw_resources = """
        /buckets/sbid1/collections/scid1;/buckets/dbid1/collections/dcid1
        /buckets/sbid2/collections/scid2;/buckets/dbid2/collections/dcid2
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
