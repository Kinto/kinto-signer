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
