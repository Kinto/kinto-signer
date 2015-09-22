from .support import unittest

import kintoupdater
import kintoclient
import mock
import pytest


class UpdaterTest(unittest.TestCase):
    @mock.patch('kintoupdater.kintoclient.create_session')
    def test_session_is_defined_if_not_passed(self, create_session):
        updater = kintoupdater.Updater(
            "bucket", "collection",
            auth=("user", "pass"))

        create_session.assert_called_with(kintoclient.DEFAULT_SERVER_URL,
                                          ('user', 'pass'))

    def test_session_is_used_if_passed(self):
        updater = kintoupdater.Updater(
            "bucket", "collection",
            session=mock.sentinel.session)
        assert updater.session == mock.sentinel.session

    def test_error_is_raised_on_missing_args(self):
        with pytest.raises(ValueError) as e:
            kintoupdater.Updater("bucket", "collection")
        assert "session or auth should be defined" in e.value

    @mock.patch('kintoupdater.Endpoints')
    def test_endpoints_is_created_by_constructor(self, endpoints):
        kintoupdater.Updater("bucket", "collection",
                             auth=("user", "pass"))
        endpoints.assert_called_with()
