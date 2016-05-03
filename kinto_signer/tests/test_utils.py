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
