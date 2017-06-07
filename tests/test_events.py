import mock
import os
import unittest

from kinto.core import events as kinto_events
from pyramid.config import Configurator

from kinto_signer import events as signer_events

from .support import BaseWebTest


here = os.path.abspath(os.path.dirname(__file__))


class Listener(object):
    def __init__(self):
        self.received = []

    def __call__(self, event):
        self.received.append(event)


listener = Listener()


def load_from_config(config, prefix):
    return listener


class ResourceEventsTest(BaseWebTest, unittest.TestCase):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.source_collection = "/buckets/alice/collections/scid"
        cls.destination_collection = "/buckets/destination/collections/dcid"

        settings['kinto.signer.resources'] = '%s;%s' % (
            cls.source_collection,
            cls.destination_collection)

        settings['kinto.signer.signer_backend'] = ('kinto_signer.signer.'
                                                   'local_ecdsa')
        settings['signer.ecdsa.private_key'] = os.path.join(
            here, 'config', 'ecdsa.private.pem')

        settings['event_listeners'] = 'ks'
        settings['event_listeners.ks.use'] = 'tests.test_events'
        return settings

    def setUp(self):
        super().setUp()
        self.app.put_json("/buckets/alice", headers=self.headers)
        self.app.put_json(self.source_collection, headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "hello"}},
                           headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "bonjour"}},
                           headers=self.headers)

    def _sign(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)

        resp = self.app.get(self.source_collection, headers=self.headers)
        data = resp.json["data"]
        self.assertEqual(data["status"], "signed")

        resp = self.app.get(self.destination_collection, headers=self.headers)
        data = resp.json["data"]
        self.assertIn("signature", data)

    def test_resource_changed_is_triggered_for_destination_bucket(self):
        self._sign()
        event = [e for e in listener.received
                 if e.payload["uri"] == "/buckets/destination" and
                 e.payload["action"] == "create"][0]
        self.assertEqual(len(event.impacted_records), 1)

        event = [e for e in listener.received
                 if e.payload["uri"] == self.destination_collection and
                 e.payload["action"] == "create"][0]
        self.assertEqual(len(event.impacted_records), 1)
        self.assertEqual(event.payload['user_id'], "plugin:kinto-signer")

    def test_resource_changed_is_triggered_for_work_in_progress(self):
        events = [e for e in listener.received
                  if e.payload["resource_name"] == "collection" and
                  e.payload["collection_id"] == "scid" and
                  e.payload["action"] == "update"]

        self.assertEqual(events[-1].payload["user_id"], "plugin:kinto-signer")
        self.assertEqual(events[-1].impacted_records[0]["new"]["status"],
                         "work-in-progress")
        self.assertIsNone(events[-1].impacted_records[0]["old"].get("status"))
        self.assertIn("basicauth:", events[-1].impacted_records[0]["new"]["last_author"])
        self.assertIsNone(events[-1].impacted_records[0]["old"].get("last_author"))

    def test_resource_changed_is_triggered_for_to_review(self):
        before = len(listener.received)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

        events = [e for e in listener.received[before:]
                  if e.payload["resource_name"] == "collection" and
                  e.payload["collection_id"] == "scid" and
                  e.payload["action"] == "update"]

        self.assertEqual(len(events), 2)
        self.assertIn("basicauth:", events[0].payload["user_id"])
        self.assertEqual(events[0].impacted_records[0]["new"]["status"], "to-review")
        self.assertNotIn("last_editor", events[0].impacted_records[0]["new"])

        self.assertEqual(events[1].payload["user_id"], "plugin:kinto-signer")
        self.assertIn("basicauth:", events[1].impacted_records[0]["new"]["last_editor"])
        self.assertEqual(events[1].impacted_records[0]["old"]["status"], "to-review")

    def test_resource_changed_is_triggered_for_source_collection(self):
        before = len(listener.received)

        self._sign()
        events = [e for e in listener.received[before:]
                  if e.payload["resource_name"] == "collection" and
                  e.payload["collection_id"] == "scid" and
                  e.payload["action"] == "update"]
        self.assertEqual(len(events), 2)
        event_tosign = events[0]
        self.assertEqual(len(event_tosign.impacted_records), 1)
        self.assertEqual(event_tosign.impacted_records[0]["new"]["status"],
                         "to-sign")
        event_signed = events[1]
        self.assertEqual(len(event_signed.impacted_records), 1)
        self.assertEqual(event_signed.impacted_records[0]["old"]["status"],
                         "to-sign")
        self.assertEqual(event_signed.impacted_records[0]["new"]["status"],
                         "signed")
        self.assertGreater(event_signed.payload['timestamp'], event_tosign.payload['timestamp'])

    def test_resource_changed_is_triggered_for_destination_collection(self):
        before = len(listener.received)

        self._sign()
        event = [e for e in listener.received[before:]
                 if e.payload["resource_name"] == "collection" and
                 e.payload.get("collection_id") == "dcid" and
                 e.payload["action"] == "update"][0]

        self.assertEqual(len(event.impacted_records), 1)
        self.assertNotEqual(event.impacted_records[0]["old"].get("signature"),
                            event.impacted_records[0]["new"]["signature"])

    def test_resource_changed_is_triggered_for_destination_creation(self):
        before = len(listener.received)

        self._sign()
        events = [e for e in listener.received[before:]
                  if e.payload["resource_name"] == "record" and
                  e.payload["collection_id"] == "dcid"]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload['action'], 'create')
        self.assertEqual(len(events[0].impacted_records), 2)
        updated = events[0].impacted_records[0]
        self.assertNotIn('old', updated)
        self.assertIn(updated['new']['title'], ('bonjour', 'hello'))

    def test_resource_changed_is_triggered_for_destination_update(self):
        record_uri = self.source_collection + "/records/xyz"
        self.app.put_json(record_uri,
                          {"data": {"title": "salam"}},
                          headers=self.headers)
        self._sign()
        self.app.patch_json(record_uri,
                            {"data": {"title": "servus"}},
                            headers=self.headers)

        before = len(listener.received)

        self._sign()
        events = [e for e in listener.received[before:]
                  if e.payload["resource_name"] == "record" and
                  e.payload["collection_id"] == "dcid"]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload['action'], 'update')
        self.assertEqual(len(events[0].impacted_records), 1)
        updated = events[0].impacted_records[0]
        self.assertIn(updated['old']['title'], 'salam')
        self.assertIn(updated['new']['title'], 'servus')

    def test_resource_changed_is_triggered_for_destination_removal(self):
        record_uri = self.source_collection + "/records/xyz"
        self.app.put_json(record_uri,
                          {"data": {"title": "servus"}},
                          headers=self.headers)
        self._sign()
        self.app.delete(record_uri, headers=self.headers)

        before = len(listener.received)
        self._sign()

        events = [e for e in listener.received[before:]
                  if e.payload["resource_name"] == "record"]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["action"], "delete")
        self.assertEqual(events[0].payload["uri"],
                         self.destination_collection + "/records/xyz")


class SignoffEventsTest(BaseWebTest, unittest.TestCase):
    events = []

    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)

        cls.source_collection = "/buckets/alice/collections/scid"
        cls.destination_collection = "/buckets/destination/collections/dcid"

        settings['kinto.signer.resources'] = '%s;%s' % (
            cls.source_collection,
            cls.destination_collection)

        settings['kinto.signer.signer_backend'] = ('kinto_signer.signer.'
                                                   'local_ecdsa')
        settings['signer.ecdsa.private_key'] = os.path.join(
            here, 'config', 'ecdsa.private.pem')
        return settings

    @classmethod
    def make_app(cls, settings=None, config=None):
        config = Configurator(settings=cls.get_app_settings())

        def on_review_received(event):
            event.request.registry.storage.create(collection_id='custom',
                                                  parent_id='',
                                                  record={'pi': 3.14})

        def on_signer_event(event):
            cls.events.append(event)

        config.add_subscriber(on_review_received, signer_events.ReviewRequested)
        config.add_subscriber(on_signer_event, signer_events.ReviewRequested)
        config.add_subscriber(on_signer_event, signer_events.ReviewRejected)
        config.add_subscriber(on_signer_event, signer_events.ReviewApproved)

        return super().make_app(config=config)

    def setUp(self):
        del self.events[:]

        self.app.put_json("/buckets/alice", headers=self.headers)
        self.app.put_json(self.source_collection, headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "hello"}},
                           headers=self.headers)
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "bonjour"}},
                           headers=self.headers)

        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-review"}},
                            headers=self.headers)

    def test_review_requested_is_triggered(self):
        assert isinstance(self.events[-1], signer_events.ReviewRequested)

    def test_events_have_details_attributes(self):
        e = self.events[-1]
        assert e.request.path == '/' + self.api_prefix + self.source_collection
        assert e.payload['uri'] == self.source_collection
        assert e.payload['collection_id'] == 'scid'
        assert e.impacted_records[0]['new']['id'] == 'scid'
        assert e.resource['source']['bucket'] == 'alice'
        assert isinstance(e.original_event, kinto_events.ResourceChanged)

    def test_review_rejected_is_triggered(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "work-in-progress"}},
                            headers=self.headers)
        assert isinstance(self.events[-1], signer_events.ReviewRejected)

    def test_review_rejected_is_not_triggered_if_not_waiting_review(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        del self.events[:]
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "work-in-progress"}},
                            headers=self.headers)
        assert len(self.events) == 0

    def test_review_rejected_is_not_triggered_when_modified_indirectly(self):
        del self.events[:]
        self.app.post_json(self.source_collection + "/records",
                           {"data": {"title": "hello"}},
                           headers=self.headers)
        assert len(self.events) == 0

    def test_review_approved_is_triggered(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        assert isinstance(self.events[-1], signer_events.ReviewApproved)

    def test_review_approved_is_not_triggered_on_resign(self):
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        del self.events[:]
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers)
        assert len(self.events) == 0

    def test_event_is_not_sent_if_rolledback(self):
        patch = mock.patch('kinto_signer.signer.local_ecdsa.ECDSASigner.sign',
                           side_effect=ValueError('boom'))
        self.addCleanup(patch.stop)
        patch.start()

        del self.events[:]
        self.app.patch_json(self.source_collection,
                            {"data": {"status": "to-sign"}},
                            headers=self.headers,
                            status=503)
        assert len(self.events) == 0

    def test_database_changes_in_subscribers_are_committed(self):
        _, count = self.storage.get_all(collection_id='custom', parent_id='')
        assert count == 1
