import unittest

import mock

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

        self.app.put_json("/buckets/alice",
                          {"permissions": {"write": ["system.Authenticated"]}},
                          headers=self.headers)
        self.app.put_json("/buckets/alice/groups/editors",
                          {"data": {"members": [self.userid,
                                                self.other_userid]}},
                          headers=self.headers)
        self.app.put_json("/buckets/alice/groups/reviewers",
                          {"data": {"members": [self.userid,
                                                self.other_userid]}},
                          headers=self.headers)
        self.app.put_json(self.source_collection, headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "hello"}},
                           headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "bonjour"}},
                           headers=self.headers)

    def get_app_settings(self, extras=None):
        settings = super(PostgresWebTest, self).get_app_settings(extras)

        settings['storage_backend'] = 'kinto.core.storage.postgresql'
        db = "postgres://postgres:postgres@localhost/testdb"
        settings['storage_url'] = db
        settings['permission_backend'] = 'kinto.core.permission.postgresql'
        settings['permission_url'] = db
        settings['cache_backend'] = 'kinto.core.cache.memory'

        self.source_collection = "/buckets/alice/collections/scid"
        self.destination_collection = "/buckets/destination/collections/dcid"

        settings['kinto.signer.resources'] = '%s;%s' % (
            self.source_collection,
            self.destination_collection)
        return settings


class CollectionStatusTest(PostgresWebTest, unittest.TestCase):

    def test_status_cannot_be_set_to_unknown_value(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "married"}},
                            headers=self.headers,
                            status=400)
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
    def get_app_settings(self, extras=None):
        settings = super(ForceReviewTest, self).get_app_settings(extras)
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


class UserGroupsTest(PostgresWebTest, unittest.TestCase):
    def get_app_settings(self, extras=None):
        settings = super(UserGroupsTest, self).get_app_settings(extras)
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
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.reviewer_headers,
                            status=403)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.editor_headers)

    def test_only_reviewers_can_ask_to_sign(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.editor_headers)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.editor_headers,
                            status=403)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.reviewer_headers)
