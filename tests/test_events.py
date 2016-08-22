import os
import unittest

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
    def get_app_settings(self, extras=None):
        settings = super(ResourceEventsTest, self).get_app_settings(extras)

        self.source_collection = "/buckets/alice/collections/scid"
        self.destination_collection = "/buckets/destination/collections/dcid"

        settings['kinto.signer.resources'] = '%s;%s' % (
            self.source_collection,
            self.destination_collection)

        settings['kinto.signer.signer_backend'] = ('kinto_signer.signer.'
                                                   'local_ecdsa')
        settings['signer.ecdsa.private_key'] = os.path.join(
            here, 'config', 'ecdsa.private.pem')

        settings['event_listeners'] = 'ks'
        settings['event_listeners.ks.use'] = 'tests.test_events'
        return settings

    def setUp(self):
        super(ResourceEventsTest, self).setUp()
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
