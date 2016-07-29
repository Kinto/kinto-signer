# def test_only_reviewers_can_change_status_to_to_sign():
#     pass

# def test_passing_from_signed_to_to_sign_is_allowed_as_a_reviewer():
#     """This is useful when the x5u certificate changed and you want
#        to retrigger a new signature."""
#     pass

# import pytest
# from kinto import main as kinto_main
# from pyramid import testing
# from pyramid.exceptions import ConfigurationError
# from requests import exceptions as requests_exceptions

# from kinto_signer import on_collection_changed, __version__ as signer_version
# from kinto_signer.signer.autograph import AutographSigner
# from kinto_signer import includeme
# from kinto_signer import utils
import mock

from . import BaseWebTest, get_user_headers
from .support import unittest


def _patch_autograph():
    # Patch calls to Autograph.
    patch = mock.patch('kinto_signer.signer.autograph.requests')
    mocked = patch.start()
    mocked.post.return_value.json.return_value = [{
        "signature": "",
        "hash_algorithm": "",
        "signature_encoding": "",
        "content-signature": "",
        "x5u": ""}]
    return patch


class CollectionStatusTest(BaseWebTest, unittest.TestCase):

    def setUp(self):
        super(CollectionStatusTest, self).setUp()
        self.headers = get_user_headers('tarte:en-pion')

        patch = _patch_autograph()
        self.addCleanup(patch.stop)

        self.app.put_json("/buckets/alice", headers=self.headers)
        self.source_collection = "/buckets/alice/collections/source"
        self.app.put_json(self.source_collection, headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "hello"}},
                           headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "bonjour"}},
                           headers=self.headers)

    def test_status_cannot_be_set_to_unknown_value(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "married"}},
                            headers=self.headers,
                            status=400)

    # XXX
    # def test_status_cannot_be_set_to_to_sign_without_review(self):
    #     self.app.patch_json(self.source_collection,
    #                         {"data": {"status": "to-sign"}},
    #                         headers=self.headers,
    #                         status=403)

    def test_status_cannot_be_set_to_signed_manually(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "signed"}},
                            headers=self.headers,
                            status=403)

    def test_status_cannot_be_maintained_as_signed_manually(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        # Signature occured, the source collection will be signed.
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "signed"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"author": "dali"}},
                            headers=self.headers)

    def test_status_cannot_be_removed_once_it_was_set(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        self.app.put_json(self.source_collection,
                          {"data": {}},
                          headers=self.headers,
                          status=403)

    def test_status_is_set_to_work_in_progress_when_records_are_posted(self):
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "work-in-progress"

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "Hallo"}},
                           headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "work-in-progress"


class UseridTest(BaseWebTest, unittest.TestCase):

    def setUp(self):
        super(UseridTest, self).setUp()
        self.headers = get_user_headers('tarte:en-pion')

        resp = self.app.get("/", headers=self.headers)
        self.userid = resp.json["user"]["id"]

        patch = _patch_autograph()
        self.addCleanup(patch.stop)

        self.app.put_json("/buckets/alice",
                          {"permissions": {"write": ["system.Authenticated"]}},
                          headers=self.headers)
        self.source_collection = "/buckets/alice/collections/source"
        self.app.put_json(self.source_collection, headers=self.headers)

    def test_last_editor_is_tracked(self):
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "Hallo"}},
                           headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["last_editor"] == self.userid

    def test_last_promoter_is_tracked(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["last_promoter"] == self.userid

    def test_last_reviewer_is_tracked(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"
        assert resp.json["data"]["last_reviewer"] == self.userid

    def test_promoter_cannot_be_reviewer(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers,
                            status=403)
        # Try again as someone else
        self.app.patch_json(self.source_collection,
                            {"data": {"statut": "to-sign"}},
                            headers=get_user_headers("Sam:Wan Heilss"))
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_editor_reviewer_promoter_cannot_be_changed_nor_removed(self):
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "Hallo"}},
                           headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=get_user_headers("Sam:Wan Heilss"))

        resp = self.app.get(self.source_collection, headers=self.headers)
        source_collection = resp.json["data"]
        assert source_collection["status"] == "signed"

        # All tracking fields are here.
        expected = ("last_editor", "last_promoter", "last_reviewer")
        assert all([f in source_collection for f in expected])

        # They cannot be changed nor removed.
        for f in expected:
            self.app.patch_json(self.source_collection,
                                {"data": {f: "changed"}},
                                headers=self.headers,
                                status=403)
            changed = source_collection.copy()
            changed.pop(f)
            self.app.put_json(self.source_collection,
                              {"data": changed},
                              headers=self.headers,
                              status=403)
