import unittest

import pytest
from pyramid.exceptions import ConfigurationError

from kinto_signer import utils


class ParseResourcesTest(unittest.TestCase):

    def test_missing_semicolumn_raises_an_exception(self):
        raw_resources = """
        foo
        bar
        """
        with pytest.raises(ConfigurationError):
            utils.parse_resources(raw_resources)

    def test_non_local_first_argument_raises_an_exception(self):
        raw_resources = """
        foo;bar
        bar;baz
        """
        with pytest.raises(ConfigurationError):
            utils.parse_resources(raw_resources)

    def test_malformed_url_raises_an_exception(self):
        raw_resources = """
        /buckets/sbid/scid;/buckets/dbid/collections/dcid
        """
        with pytest.raises(ConfigurationError):
            utils.parse_resources(raw_resources)

    def test_outnumbered_urls_raises_an_exception(self):
        raw_resources = (
            "/buckets/sbid/scid;"
            "/buckets/dbid/collections/dcid;"
            "/buckets/dbid/collections/dcid;"
            "/buckets/sbid/scid;")
        with pytest.raises(ConfigurationError):
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

    def test_a_preview_collection_is_supported(self):
        raw_resources = (
            "/buckets/stage/collections/cid;"
            "/buckets/preview/collections/cid;"
            "/buckets/prod/collections/cid;"
        )
        resources = utils.parse_resources(raw_resources)
        assert resources == {
            '/buckets/stage/collections/cid': {
                'source': {
                    'bucket': 'stage',
                    'collection': 'cid'
                },
                'preview': {
                    'bucket': 'preview',
                    'collection': 'cid'
                },
                'destination': {
                    'bucket': 'prod',
                    'collection': 'cid'
                }
            }
        }

    def test_resources_should_be_space_separated(self):
        raw_resources = (
            "/buckets/sbid1/collections/scid;/buckets/dbid1/collections/dcid,"
            "/buckets/sbid2/collections/scid;/buckets/dbid2/collections/dcid"
        )
        with self.assertRaises(ConfigurationError):
            utils.parse_resources(raw_resources)

        raw_resources = (
            "sbid1/scid;dbid1/dcid,sbid2/scid;dbid2/dcid"
        )
        with self.assertRaises(ConfigurationError):
            utils.parse_resources(raw_resources)

    def test_resources_must_be_valid_names(self):
        raw_resources = (
            "/buckets/sbi+d1/collections/scid;/buckets/dbid1/collections/dci,d"
        )
        with self.assertRaises(ConfigurationError):
            utils.parse_resources(raw_resources)
