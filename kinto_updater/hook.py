from cliquet.events import ResourceChanged
from cliquet.utils import current_service, COMPARISON
from cliquet.storage import Filter

from kinto_updater import Updater

import kinto_client


def sign_and_update_remote(event, client):
    request = event.request
    registry = request.registry
    payload = event.payload
    storage = registry.storage
    # service = current_service(request).

    bucket_id = payload['bucket_id']
    collection_id = payload['collection_id']

    # First, get the last time the collection was pushed.
    parent_id = "/buckets/%s" % bucket_id
    collection_data = storage.get_record(
        parent_id=parent_id,
        collection_id='collection',
        object_id=collection_id)
    last_sync = int(collection_data.get('last_sync', 0))

    # Get the list of records that has been updated since the last time we
    # updated them.
    parent_id = "/buckets/%s/collections/%s" % (bucket_id, colllection_id)
    all_records = storage.get_records(
        parent_id=parent_id,
        collection_id='record',
        filters=filters)

    # Get the new records now, so we minimize the risks of them being updated
    # when computing the signature.
    filters = [Filter('last_modified', last_sync, COMPARISON.GT), ]
    new_records = storage.get_records(parent_id=parent_id, collection_id='record',
                                      filters=filters)

    # Compute the hash of the entire collection.
    new_hash = hasher.compute_hash(all_records)
    signature = config.signer_instance.sign(new_hash)

    # Update the remote collection.
    with client.batch() as batch:
        for record in new_records:
            batch.update_record(record=record, id=record['id'], safe=False)
        batch.patch_collection(data={'signature': signature})


def includeme(config):
    # Process settings to remove storage wording.
    settings = config.get_settings()

    expected_bucket = settings.get('kinto_updater.bucket')
    expected_collection = settings.get('kinto_updater.collection')

    updater = Updater(expected_bucket, expected_collection, settings={
        'private_key': 'test.pem'
    })
    config.registry.updater = updater

    remote_url = settings['kinto_updater.remote_server_url']
    remote = kinto_client.Client(server_url=remote_url, bucket=expected_bucket,
                                 collection=expected_collection,
                                 auth="user:password")

    def on_resource_changed(event):
        payload = event.payload
        resource_name = payload['resource_name']
        action = payload['action']

        correct_bucket = payload.get('bucket_id') == expected_bucket
        correct_coll = payload.get('collection_id') == expected_collection
        is_coll = resource_name == 'collection'
        is_creation = action in ('create', 'update')

        if correct_coll and correct_bucket:
            if is_creation and is_coll:
                should_sign = any([True for r in event.impacted_records
                                   if r['new'].get('status') == 'unsigned'])
                if should_sign:
                    sign_and_update_remote(event, remote)

    config.add_subscriber(on_resource_changed, ResourceChanged)
