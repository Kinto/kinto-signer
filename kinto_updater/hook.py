from cliquet.events import ResourceChanged
from cliquet.utils import COMPARISON
from cliquet.storage import Filter
import kinto_client

from kinto_updater import hasher, signer


class RemoteUpdater(object):

    def __init__(self, remote, event):
        self.remote = remote

        # Handle a few shortcuts to ease the reading of the script.
        self.request = event.request
        self.registry = self.request.registry
        self.payload = event.payload
        self.storage = self.registry.storage
        self.signer = self.registry.signer
        self.bucket_id = self.payload['bucket_id']
        self.collection_id = self.payload['collection_id']
        # service = current_service(request).

    def get_collection_records(self, last_modified=None):
        # If a last_modified value was specified, filter on it.
        storage_kwargs = {}
        if last_modified is not None:
            gt_last_modified = Filter('last_modified', last_modified,
                                      COMPARISON.GT)
            storage_kwargs['filters'] = [gt_last_modified, ]

        parent_id = "/buckets/%s/collections/%s" % (
            self.bucket_id, self.collection_id)

        records, _ = self.storage.get_all(
            parent_id=parent_id,
            collection_id='record', **storage_kwargs)
        return records

    def get_remote_last_modified(self):
        endpoint = self.remote._get_endpoint('records')
        # XXX Replace with a HEAD request.
        _, headers = self.remote.session.request('get', endpoint)
        return int(headers['Etag'].strip('"'))

    def update_remote(self, new_hash, signature):
        last_modified = self.get_remote_last_modified()
        new_records = self.get_collection_records(last_modified)

        # Update the remote collection.
        with self.remote.batch() as batch:
            for record in new_records:
                batch.update_record(data=record, id=record['id'], safe=False)
            batch.patch_collection(data={'signature': signature})

    def sign_and_update_remote(self):
        """Sign the specified collection.

        1. Get all the records of the collection;
        2. Compute a hash of these records;
        3. Ask the signer for a signature;
        4. Send all records since the last_modified field of the Authoritative
           server;
        5. Send the signature to the Authoritative server.
        """
        records = self.get_collection_records()
        new_hash = hasher.compute_hash(records)
        signature = self.signer.sign(new_hash)
        self.update_remote(new_hash, signature)


def includeme(config):
    # Process settings to remove storage wording.
    settings = config.get_settings()

    expected_bucket = settings.get('kinto_updater.bucket')
    expected_collection = settings.get('kinto_updater.collection')

    priv_key = settings.get('kinto_updater.private_key')
    config.registry.signer = signer.RSABackend({'private_key': priv_key})

    remote_url = settings['kinto_updater.remote_server_url']

    # XXX Get the auth from settings.
    remote = kinto_client.Client(server_url=remote_url, bucket=expected_bucket,
                                 collection=expected_collection,
                                 auth=('user', 'p4ssw0rd'))

    def on_resource_changed(event):
        payload = event.payload
        resource_name = payload['resource_name']
        action = payload['action']

        # XXX Replace the filtering by events predicates (on the next Kinto
        # release)
        correct_bucket = payload.get('bucket_id') == expected_bucket
        correct_coll = payload.get('collection_id') == expected_collection
        is_coll = resource_name == 'collection'
        is_creation = action in ('create', 'update')

        if correct_coll and correct_bucket:
            if is_creation and is_coll:
                should_sign = any([True for r in event.impacted_records
                                   if r['new'].get('status') == 'to-sign'])
                if should_sign:
                    updater = RemoteUpdater(remote, event)
                    updater.sign_and_update_remote()

    config.add_subscriber(on_resource_changed, ResourceChanged)
