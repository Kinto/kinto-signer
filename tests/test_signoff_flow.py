import random
import re
import string
import unittest

import mock

from kinto.core.testing import FormattedErrorMixin
from kinto.core.errors import ERRORS
from .support import BaseWebTest, get_user_headers


RE_ISO8601 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00")


class PostgresWebTest(BaseWebTest):
    source_bucket = "/buckets/alice"
    source_collection = "/buckets/alice/collections/scid"
    destination_bucket = "/buckets/alice"
    destination_collection = "/buckets/alice/collections/dcid"

    def setUp(self):
        super(PostgresWebTest, self).setUp()
        # Patch calls to Autograph.
        patch = mock.patch('kinto_signer.signer.autograph.requests')
        self.addCleanup(patch.stop)
        self.mocked_autograph = patch.start()

        def fake_sign():
            fake_signature = "".join(random.sample(string.ascii_lowercase, 10))
            return [{
                "signature": "",
                "hash_algorithm": "",
                "signature_encoding": "",
                "content-signature": fake_signature,
                "x5u": ""
            }]

        self.mocked_autograph.post.return_value.json.side_effect = fake_sign

    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        settings['storage_backend'] = 'kinto.core.storage.postgresql'
        db = "postgres://postgres:postgres@localhost/testdb"
        settings['storage_url'] = db
        settings['permission_backend'] = 'kinto.core.permission.postgresql'
        settings['permission_url'] = db
        settings['cache_backend'] = 'kinto.core.cache.memory'

        settings['kinto.signer.resources'] = '%s -> %s' % (
            cls.source_collection,
            cls.destination_collection)
        return settings


class SignoffWebTest(PostgresWebTest):
    def setUp(self):
        super(SignoffWebTest, self).setUp()
        self.headers = get_user_headers('tarte:en-pion')
        resp = self.app.get("/", headers=self.headers)
        self.userid = resp.json["user"]["id"]

        self.other_headers = get_user_headers('Sam:Wan Heilss')
        resp = self.app.get("/", headers=self.other_headers)
        self.other_userid = resp.json["user"]["id"]

        # Source bucket
        self.app.put_json(self.source_bucket,
                          {"permissions": {"write": ["system.Authenticated"]}},
                          headers=self.headers)

        # Editors and reviewers group
        self.app.put_json(self.source_bucket + "/groups/editors",
                          {"data": {"members": [self.userid,
                                                self.other_userid]}},
                          headers=self.headers)
        self.app.put_json(self.source_bucket + "/groups/reviewers",
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


class CollectionStatusTest(SignoffWebTest, FormattedErrorMixin, unittest.TestCase):
    def test_status_can_be_refreshed_even_if_never_signed(self):
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert "last_signature_date" not in resp.json["data"]

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-resign"}},
                            headers=self.headers)

        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "work-in-progress"
        assert "last_signature_date" in resp.json["data"]
        # The review request / approval field are not set.
        assert "last_review_date" not in resp.json["data"]
        assert "last_review_request_date" not in resp.json["data"]

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


class ForceReviewTest(SignoffWebTest, unittest.TestCase):
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


class RefreshSignatureTest(SignoffWebTest, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)
        settings['signer.to_review_enabled'] = 'true'
        settings['signer.group_check_enabled'] = 'true'
        return settings

    def setUp(self):
        super().setUp()
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_editor_can_retrigger_a_signature(self):
        # Editor retriggers a signature, without going through review.
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-resign"}},
                            headers=self.headers)

        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

        # Old way (status: to-sign)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_reviewer_can_retrigger_a_signature(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-resign"}},
                            headers=self.other_headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

        # Old way (status: to-sign)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_non_reviewer_can_retrigger_a_signature(self):
        writer_headers = get_user_headers('walter:white')
        resp = self.app.get("/", headers=writer_headers)
        writer_userid = resp.json["user"]["id"]
        self.app.patch_json(self.source_bucket, {
            "permissions": {
                "write": [writer_userid]
            }
        }, headers=self.headers)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-resign"}},
                            headers=writer_headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

        # Old way (status: to-sign)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=writer_headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"

    def test_signature_can_be_refreshed_with_pending_changes(self):
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "pending change"}},
                           headers=self.headers)

        resp = self.app.get(self.destination_collection, headers=self.headers)
        before_signature = resp.json["data"]["signature"]["content-signature"]

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-resign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "work-in-progress"

        resp = self.app.get(self.destination_collection, headers=self.headers)
        assert resp.json["data"]["signature"]["content-signature"] != before_signature


class TrackingFieldsTest(SignoffWebTest, unittest.TestCase):

    def last_edit_by_and_date_are_tracked(self):
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "Hallo"}},
                           headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["last_edit_by"] == self.userid
        assert RE_ISO8601.match(resp.json["data"]["last_edit_date"])

    def test_last_review_request_by_and_date_are_tracked(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["last_review_request_by"] == self.userid
        assert RE_ISO8601.match(resp.json["data"]["last_review_request_date"])

    def test_last_review_by_and_date_are_tracked(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"
        assert resp.json["data"]["last_review_by"] == self.userid
        assert RE_ISO8601.match(resp.json["data"]["last_review_date"])
        assert resp.json["data"]["last_signature_by"] == self.userid
        assert RE_ISO8601.match(resp.json["data"]["last_signature_date"])

    def test_last_review_differs_from_last_signature_on_refresh_signature(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json["data"]["status"] == "signed"
        last_reviewer = resp.json["data"]["last_review_by"]

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-resign"}},
                            headers=self.headers)
        metadata = self.app.get(self.source_collection, headers=self.headers).json["data"]
        assert metadata["status"] == "signed"

        assert metadata["last_signature_date"] != metadata["last_review_date"]
        assert last_reviewer == metadata["last_review_by"]

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
        expected = ("last_edit_by", "last_edit_date", "last_review_request_by",
                    "last_review_request_date", "last_review_by", "last_review_date",
                    "last_signature_by", "last_signature_date")
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


class UserGroupsTest(SignoffWebTest, FormattedErrorMixin, unittest.TestCase):
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


class SpecificUserGroupsTest(SignoffWebTest, FormattedErrorMixin, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.source_collection1 = "/buckets/alice/collections/cid1"
        cls.source_collection2 = "/buckets/alice/collections/cid2"

        settings['kinto.signer.resources'] = "%s -> %s\n%s -> %s" % (
            cls.source_collection1,
            cls.source_collection1.replace("alice", "destination"),
            cls.source_collection2,
            cls.source_collection2.replace("alice", "destination"))

        settings['signer.group_check_enabled'] = 'false'
        settings['signer.alice.cid1.group_check_enabled'] = 'true'
        settings['signer.alice.cid1.editors_group'] = 'editeurs'
        settings['signer.alice.cid1.reviewers_group'] = 'revoyeurs'
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


class PreviewCollectionTest(SignoffWebTest, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.preview_bucket = "/buckets/preview"
        cls.preview_collection = cls.preview_bucket + "/collections/pcid"

        settings['signer.to_review_enabled'] = 'true'
        settings['kinto.signer.resources'] = '%s -> %s -> %s' % (
            cls.source_collection,
            cls.preview_collection,
            cls.destination_collection)
        return settings

    def test_the_preview_collection_is_updated_and_signed(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        self.app.get(self.preview_bucket, headers=self.headers)

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

    def test_the_preview_collection_is_also_resigned(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        resp = self.app.get(self.preview_collection, headers=self.headers)
        signature_preview_before = resp.json['data']['signature']
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)
        resp = self.app.get(self.destination_collection, headers=self.headers)
        signature_destination_before = resp.json['data']['signature']
        # status is signed.
        resp = self.app.get(self.source_collection, headers=self.headers)
        assert resp.json['data']['status'] == 'signed'

        # Resign.
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-resign"}},
                            headers=self.headers)

        resp = self.app.get(self.destination_collection, headers=self.headers)
        signature_destination_after = resp.json['data']['signature']
        assert signature_destination_before != signature_destination_after
        resp = self.app.get(self.preview_collection, headers=self.headers)
        signature_preview_after = resp.json['data']['signature']
        assert signature_preview_before != signature_preview_after

        # Resign the old way.
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        resp = self.app.get(self.preview_collection, headers=self.headers)
        signature_preview_before = signature_preview_after
        signature_preview_after = resp.json['data']['signature']
        assert signature_preview_before != signature_preview_after

    def test_the_preview_collection_is_emptied_when_source_records_are_deleted(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)

        resp = self.app.get(self.source_collection + "/records", headers=self.headers)
        records = resp.json["data"]
        for r in records:
            self.app.delete(self.source_collection + "/records/" + r["id"], headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        resp = self.app.get(self.preview_collection + "/records", headers=self.headers)
        records = resp.json["data"]
        assert len(records) == 0

    def test_the_preview_collection_is_emptied_when_source_is_deleted(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.other_headers)

        self.app.delete(self.source_collection + "/records", headers=self.headers).json["data"]
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        resp = self.app.get(self.preview_collection + "/records", headers=self.headers)
        records = resp.json["data"]
        assert len(records) == 0


class NoReviewNoPreviewTest(SignoffWebTest, unittest.TestCase):
    """
    If review is disabled for a collection, we don't create the preview collection
    nor copy the records there.
    """
    source_bucket = "/buckets/dev"
    source_collection = "/buckets/dev/collections/normandy"
    preview_bucket = "/buckets/stage"
    preview_collection = "/buckets/stage/collections/normandy"
    destination_bucket = "/buckets/prod"
    destination_collection = "/buckets/prod/collections/normandy"

    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        settings['signer.to_review_enabled'] = 'true'
        settings['signer.group_check_enabled'] = 'true'

        settings['kinto.signer.resources'] = ' -> '.join((
            cls.source_bucket,
            cls.preview_bucket,
            cls.destination_bucket))

        settings['signer.dev.normandy.to_review_enabled'] = 'false'
        settings['signer.dev.normandy.group_check_enabled'] = 'false'

        return settings

    def setUp(self):
        super(NoReviewNoPreviewTest, self).setUp()
        # Make the preview bucket readable (to obtain explicit 404 when collections
        # don't exist instead of ambiguous 403)
        self.app.put_json(self.preview_bucket, {
            "permissions": {
                "read": ["system.Everyone"]
            }
        }, headers=self.headers)

    def test_the_preview_collection_is_not_created(self):
        self.app.put_json(self.source_bucket + "/collections/onecrl",
                          status=201, headers=self.headers)
        self.app.put_json(self.source_collection, headers=self.headers)

        self.app.get(self.preview_bucket + "/collections/onecrl",
                     status=200, headers=self.headers)
        self.app.get(self.preview_collection, status=404, headers=self.headers)

    def test_the_preview_collection_is_not_updated(self):
        r = self.app.get(self.destination_collection + "/records", headers=self.headers)
        before = len(r.json["data"])
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "Hallo"}},
                           headers=self.headers)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)

        # The preview still does not exist :)
        self.app.get(self.preview_collection, status=404, headers=self.headers)
        # Prod was updated.
        r = self.app.get(self.destination_collection + "/records", headers=self.headers)
        assert len(r.json["data"]) > before


class PerBucketTest(SignoffWebTest, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.source_bucket = "/buckets/stage"
        cls.source_collection = cls.source_bucket + "/collections/cid"
        cls.preview_bucket = "/buckets/preview"
        cls.preview_collection = cls.preview_bucket + "/collections/cid"
        cls.destination_bucket = "/buckets/prod"
        cls.destination_collection = cls.destination_bucket + "/collections/cid"

        settings['kinto.signer.resources'] = ' -> '.join([
            cls.source_bucket,
            cls.preview_bucket,
            cls.destination_bucket])

        settings['signer.to_review_enabled'] = 'true'
        settings['signer.stage.specific.to_review_enabled'] = 'false'

        settings['signer.stage.specific.autograph.hawk_id'] = 'for-specific'
        return settings

    def test_destination_and_preview_collections_are_created_and_signed(self):
        col_uri = "/collections/pim"
        self.app.put(self.source_bucket + col_uri, headers=self.headers)

        data = self.app.get(self.preview_bucket + col_uri, headers=self.headers).json['data']
        assert "signature" in data

        data = self.app.get(self.destination_bucket + col_uri, headers=self.headers).json['data']
        assert "signature" in data

        # Source status was left untouched (ie. missing here)
        data = self.app.get(self.source_bucket + col_uri, headers=self.headers).json['data']
        assert "status" not in data

    def test_review_settings_can_be_overriden_for_a_specific_collection(self):
        # review is not enabled for this particular one, sign directly!
        self.app.put_json(self.source_bucket + "/collections/specific",
                          {"data": {"status": "to-sign"}},
                          headers=self.headers)

    def test_signer_can_be_specified_per_collection(self):
        self.mocked_autograph.post.reset_mock()
        self.app.put_json(self.source_bucket + "/collections/specific",
                          {"data": {"status": "to-sign"}},
                          headers=self.headers)

        args, kwargs = self.mocked_autograph.post.call_args_list[0]
        assert args[0].startswith('http://localhost:8000')  # global.
        assert kwargs['auth'].credentials['id'] == 'for-specific'
        assert kwargs['auth'].credentials['key'].startswith('fs5w')  # global in signer.ini


class GroupCreationTest(PostgresWebTest, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.source_bucket = "/buckets/stage"
        cls.preview_bucket = "/buckets/preview"
        cls.destination_bucket = "/buckets/prod"

        settings['signer.to_review_enabled'] = 'true'

        settings['kinto.signer.editors_group'] = 'best-editors'
        settings['kinto.signer.reviewers_group'] = '{collection_id}-reviewers'
        settings['kinto.signer.resources'] = ';'.join([
            cls.source_bucket,
            cls.preview_bucket,
            cls.destination_bucket])

        cls.editors_group = cls.source_bucket + "/groups/best-editors"
        cls.reviewers_group = cls.source_bucket + "/groups/good-reviewers"
        cls.source_collection = cls.source_bucket + "/collections/good"

        return settings

    def setUp(self):
        super(GroupCreationTest, self).setUp()

        resp = self.app.get("/", headers=self.headers)
        self.userid = resp.json["user"]["id"]

        self.app.put(self.source_bucket, headers=self.headers)

        self.other_headers = get_user_headers('otra:persona')
        resp = self.app.get("/", headers=self.other_headers)
        self.other_userid = resp.json["user"]["id"]

    def test_groups_are_not_touched_if_existing(self):
        resp = self.app.put(self.editors_group, headers=self.headers)
        before = resp.json['data']['last_modified']

        self.app.put(self.source_collection, headers=self.headers)

        resp = self.app.get(self.editors_group, headers=self.headers)
        after = resp.json['data']['last_modified']

        assert before == after

    def test_groups_are_created_if_missing(self):
        self.app.get(self.editors_group, headers=self.headers, status=404)
        self.app.get(self.reviewers_group, headers=self.headers, status=404)

        self.app.put(self.source_collection, headers=self.headers)

        self.app.get(self.editors_group, headers=self.headers)
        self.app.get(self.reviewers_group, headers=self.headers)

    def test_groups_are_allowed_to_write_the_source_collection(self):
        body = {'data': {'members': [self.other_userid]}}
        self.app.put_json(self.editors_group, body, headers=self.headers)

        self.app.put(self.source_collection, headers=self.headers)

        self.app.post_json(self.source_collection + '/records',
                           headers=self.other_headers, status=201)

    def test_events_are_sent(self):
        patch = mock.patch('kinto_signer.utils.notify_resource_event')
        mocked = patch.start()
        self.addCleanup(patch.stop)

        self.app.put(self.source_collection, headers=self.headers)

        args, kwargs = mocked.call_args_list[0]
        _, fakerequest = args
        assert fakerequest['method'] == 'PUT'
        assert fakerequest['path'] == '/buckets/stage/groups/best-editors'
        assert kwargs['resource_name'] == 'group'

    def test_groups_permissions_include_current_user_only(self):
        self.app.put(self.source_collection, headers=self.headers)

        r = self.app.get(self.editors_group, headers=self.headers).json
        assert r['permissions']['write'] == [self.userid]
        r = self.app.get(self.reviewers_group, headers=self.headers).json
        assert r['permissions']['write'] == [self.userid]

    def test_editors_contains_current_user_as_member_by_default(self):
        self.app.put(self.source_collection, headers=self.headers)

        r = self.app.get(self.editors_group, headers=self.headers).json
        assert r['data']['members'] == [self.userid]
        r = self.app.get(self.reviewers_group, headers=self.headers).json
        assert r['data']['members'] == []

    def test_groups_are_not_touched_if_already_exist(self):
        resp = self.app.put(self.editors_group, headers=self.headers)
        editors_timetamp = resp.json['data']['last_modified']
        resp = self.app.put(self.reviewers_group, headers=self.headers)
        reviewers_timetamp = resp.json['data']['last_modified']

        self.app.put(self.source_collection, headers=self.headers)

        r = self.app.get(self.editors_group, headers=self.headers).json
        assert r['data']['last_modified'] == editors_timetamp
        r = self.app.get(self.reviewers_group, headers=self.headers).json
        assert r['data']['last_modified'] == reviewers_timetamp

    def test_groups_are_not_created_if_not_allowed(self):
        # Allow this other user to create collections.
        body = {'permissions': {'collection:create': [self.other_userid]}}
        self.app.patch_json(self.source_bucket, body, headers=self.headers)

        # Create the collection.
        self.app.put(self.source_collection, headers=self.other_headers)

        # Groups were not created.
        self.app.get(self.editors_group, headers=self.headers, status=404)
        self.app.get(self.reviewers_group, headers=self.headers, status=404)

    def test_groups_are_created_if_allowed_via_group_create_perm(self):
        # Allow this other user to create collections and groups.
        body = {'permissions': {'collection:create': [self.other_userid],
                                'group:create': [self.other_userid]}}
        self.app.patch_json(self.source_bucket, body, headers=self.headers)

        # Create the collection.
        self.app.put(self.source_collection, headers=self.other_headers)

        self.app.get(self.editors_group, headers=self.headers)
        self.app.get(self.reviewers_group, headers=self.headers)
