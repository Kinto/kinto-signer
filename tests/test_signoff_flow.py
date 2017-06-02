import unittest

import mock

from kinto.core.testing import FormattedErrorMixin
from kinto.core.errors import ERRORS
from .support import BaseWebTest, get_user_headers


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


class PostgresWebTest(BaseWebTest):
    def setUp(self):
        super(PostgresWebTest, self).setUp()
        patch = _patch_autograph()
        self.addCleanup(patch.stop)

        self.headers = get_user_headers('tarte:en-pion')
        resp = self.app.get("/", headers=self.headers)
        self.userid = resp.json["user"]["id"]

        self.other_headers = get_user_headers('Sam:Wan Heilss')
        resp = self.app.get("/", headers=self.other_headers)
        self.other_userid = resp.json["user"]["id"]

        # Source bucket
        self.app.put_json("/buckets/alice",
                          {"permissions": {"write": ["system.Authenticated"]}},
                          headers=self.headers)

        # Editors and reviewers group
        self.app.put_json("/buckets/alice/groups/editors",
                          {"data": {"members": [self.userid,
                                                self.other_userid]}},
                          headers=self.headers)
        self.app.put_json("/buckets/alice/groups/reviewers",
                          {"data": {"members": [self.userid,
                                                self.other_userid]}},
                          headers=self.headers)

        # Source collection with 2 records
        self.app.put_json(self.source_collection, headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "hello"}},
                           headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "bonjour"}},
                           headers=self.headers)

    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        settings['storage_backend'] = 'kinto.core.storage.postgresql'
        db = "postgres://postgres:postgres@localhost/testdb"
        settings['storage_url'] = db
        settings['permission_backend'] = 'kinto.core.permission.postgresql'
        settings['permission_url'] = db
        settings['cache_backend'] = 'kinto.core.cache.memory'

        cls.source_collection = "/buckets/alice/collections/scid"
        cls.destination_collection = "/buckets/destination/collections/dcid"

        settings['kinto.signer.resources'] = '%s;%s' % (
            cls.source_collection,
            cls.destination_collection)
        return settings


class CollectionStatusTest(PostgresWebTest, FormattedErrorMixin, unittest.TestCase):

    def test_status_cannot_be_set_to_unknown_value(self):
        resp = self.app.patch_json(self.source_collection,
                                   {"data": {"status": "married"}},
                                   headers=self.headers,
                                   status=400)
        self.assertFormattedError(response=resp,
                                  code=400,
                                  errno=ERRORS.INVALID_POSTED_DATA,
                                  error="Bad Request",
                                  message="Invalid status 'married'")
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "work-in-progress"

    def test_status_cannot_be_set_to_signed_manually(self):
        resp = self.app.patch_json(self.source_collection,
                                   {"data": {"status": "signed"}},
                                   headers=self.headers,
                                   status=400)
        assert resp.json["message"] == "Cannot set status to 'signed'"
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "work-in-progress"

    def test_status_can_be_set_to_work_in_progress_manually(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "work-in-progress"}},
                            headers=self.headers)

    def test_status_can_be_maintained_as_signed_manually(self):
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
                          status=400)

    def test_status_cannot_be_emptied_once_it_was_set(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        self.app.put_json(self.source_collection,
                          {"data": {"status": ""}},
                          headers=self.headers,
                          status=400)

    def test_status_can_be_reset(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "to-review"

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


class ForceReviewTest(PostgresWebTest, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)
        settings['signer.to_review_enabled'] = 'true'
        return settings

    def test_status_cannot_be_set_to_to_sign_without_review(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers,
                            status=400)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "work-in-progress"

    def test_passing_from_signed_to_to_sign_is_allowed(self):
        """This is useful when the x5u certificate changed and you want
           to retrigger a new signature."""
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)
        resp = self.app.get(self.source_collection, headers=self.other_headers)
        assert resp.json["data"]["status"] == "signed"

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_editor_cannot_be_reviewer(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers,
                            status=403)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "to-review"

        # Try again as someone else
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_editor_can_retrigger_a_signature(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)

        # Now collection is signed.
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

        # Editor retriggers a signature, without going through review.
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)

        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"


class TrackingFieldsTest(PostgresWebTest, unittest.TestCase):

    def last_author_is_tracked(self):
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "Hallo"}},
                           headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["last_author"] == self.userid

    def test_last_editor_is_tracked(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["last_editor"] == self.userid

    def test_last_reviewer_is_tracked(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"
        assert resp.json["data"]["last_reviewer"] == self.userid

    def test_editor_can_be_reviewer(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_editor_reviewer_editor_cannot_be_changed_nor_removed(self):
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "Hallo"}},
                           headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)

        resp = self.app.get(self.source_collection, headers=self.headers)
        source_collection = resp.json["data"]
        assert source_collection["status"] == "signed"

        # All tracking fields are here.
        expected = ("last_author", "last_editor", "last_reviewer")
        assert all([f in source_collection for f in expected])

        # They cannot be changed nor removed.
        for f in expected:
            self.app.patch_json(self.source_collection,
                                {"data": {f: "changed"}},
                                headers=self.headers,
                                status=400)
            changed = source_collection.copy()
            changed.pop(f)
            self.app.put_json(self.source_collection,
                              {"data": changed},
                              headers=self.headers,
                              status=400)


class UserGroupsTest(PostgresWebTest, FormattedErrorMixin, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)
        settings['signer.group_check_enabled'] = 'true'
        return settings

    def setUp(self):
        super(UserGroupsTest, self).setUp()
        self.editor_headers = get_user_headers('edith:her')
        resp = self.app.get("/", headers=self.editor_headers)
        self.editor = resp.json["user"]["id"]

        self.editor_headers = get_user_headers('emo:billier')
        resp = self.app.get("/", headers=self.editor_headers)
        self.editor = resp.json["user"]["id"]

        self.reviewer_headers = get_user_headers('ray:weaver')
        resp = self.app.get("/", headers=self.reviewer_headers)
        self.reviewer = resp.json["user"]["id"]

        self.app.put_json("/buckets/alice/groups/editors",
                          {"data": {"members": [self.editor]}},
                          headers=self.headers)

        self.app.put_json("/buckets/alice/groups/reviewers",
                          {"data": {"members": [self.reviewer]}},
                          headers=self.headers)

    def test_only_editors_can_ask_to_review(self):
        resp = self.app.patch_json(self.source_collection,
                                   {"data": {"status": "to-review"}},
                                   headers=self.reviewer_headers,
                                   status=403)
        self.assertFormattedError(response=resp,
                                  code=403,
                                  errno=ERRORS.FORBIDDEN,
                                  error="Forbidden",
                                  message="Not in editors group")

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.editor_headers)

    def test_only_reviewers_can_ask_to_sign(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.editor_headers)

        resp = self.app.patch_json(self.source_collection,
                                   {"data": {"status": "to-sign"}},
                                   headers=self.editor_headers,
                                   status=403)
        self.assertFormattedError(response=resp,
                                  code=403,
                                  errno=ERRORS.FORBIDDEN,
                                  error="Forbidden",
                                  message="Not in reviewers group")

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.reviewer_headers)


class SpecificUserGroupsTest(PostgresWebTest, FormattedErrorMixin, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.source_collection1 = "/buckets/alice/collections/cid1"
        cls.source_collection2 = "/buckets/alice/collections/cid2"

        settings['kinto.signer.resources'] = "%s;%s %s;%s" % (
            cls.source_collection1,
            cls.source_collection1.replace("alice", "destination"),
            cls.source_collection2,
            cls.source_collection2.replace("alice", "destination"))

        settings['signer.group_check_enabled'] = 'false'
        settings['signer.alice_cid1.group_check_enabled'] = 'true'
        settings['signer.alice_cid1.editors_group'] = 'editeurs'
        settings['signer.alice_cid1.reviewers_group'] = 'revoyeurs'
        return settings

    def setUp(self):
        super(SpecificUserGroupsTest, self).setUp()

        self.app.put_json(self.source_collection1, headers=self.headers)
        self.app.put_json(self.source_collection2, headers=self.headers)

        self.someone_headers = get_user_headers('sam:wan')

        self.editor_headers = get_user_headers('emo:billier')
        resp = self.app.get("/", headers=self.editor_headers)
        self.editor = resp.json["user"]["id"]

        self.app.put_json("/buckets/alice/groups/editeurs",
                          {"data": {"members": [self.editor]}},
                          headers=self.headers)

    def test_editors_can_ask_to_review_if_not_specificly_configured(self):
        self.app.patch_json(self.source_collection2,
                            {"data": {"status": "to-review"}},
                            headers=self.someone_headers,
                            status=200)

    def test_only_specific_editors_can_ask_to_review(self):
        resp = self.app.patch_json(self.source_collection1,
                                   {"data": {"status": "to-review"}},
                                   headers=self.someone_headers,
                                   status=403)
        self.assertFormattedError(response=resp,
                                  code=403,
                                  errno=ERRORS.FORBIDDEN,
                                  error="Forbidden",
                                  message="Not in editeurs group")

    def test_only_reviewers_can_ask_to_sign(self):
        self.app.patch_json(self.source_collection1,
                            {"data": {"status": "to-review"}},
                            headers=self.editor_headers)
        resp = self.app.patch_json(self.source_collection1,
                                   {"data": {"status": "to-sign"}},
                                   headers=self.editor_headers,
                                   status=403)
        self.assertFormattedError(response=resp,
                                  code=403,
                                  errno=ERRORS.FORBIDDEN,
                                  error="Forbidden",
                                  message="Not in revoyeurs group")


class PreviewCollectionTest(PostgresWebTest, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.preview_collection = "/buckets/preview/collections/pcid"

        settings['signer.to_review_enabled'] = 'true'
        settings['kinto.signer.resources'] = '%s;%s;%s' % (
            cls.source_collection,
            cls.preview_collection,
            cls.destination_collection)
        return settings

    def test_the_preview_collection_does_not_exist_at_first(self):
        self.app.get(self.preview_collection, headers=self.headers, status=403)

    def test_the_preview_collection_is_updated_and_signed(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        resp = self.app.get(self.preview_collection, headers=self.headers)
        assert 'signature' in resp.json['data']

        resp = self.app.get(self.preview_collection + '/records',
                            headers=self.headers)
        assert len(resp.json['data']) == 2

    def test_the_preview_collection_receives_kinto_admin_ui_attributes(self):
        self.app.patch_json(self.source_collection, {
            "data": {
                "status": "to-review",
                "displayFields": ["age"]
            }},
            headers=self.headers)

        resp = self.app.get(self.preview_collection, headers=self.headers)
        assert resp.json['data']['displayFields'] == ['age']
