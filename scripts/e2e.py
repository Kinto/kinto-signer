import random
from string import hexdigits
import argparse

from kinto_http import Client
from kinto_signer.serializer import canonical_json
from kinto_signer.hasher import compute_hash
from kinto_signer.signer.local_ecdsa import ECDSASigner


DEFAULT_SERVER = 'http://localhost:8888/v1'
DEFAULT_AUTH = 'user:pass'
SOURCE_BUCKET = 'alice'
DEST_BUCKET = SOURCE_BUCKET
SOURCE_COL = 'source'
DEST_COL = 'destination'


def _rand(size=10):
    return ''.join([random.choice(hexdigits) for _ in range(size)])


def collection_timestamp(client):
    # XXXX Waiting https://github.com/Kinto/kinto-http.py/issues/77
    endpoint = client.get_endpoint('records')
    record_resp, headers = client.session.request('get', endpoint)
    return headers.get('ETag', '').strip('"')


def upload_records(client, num):
    records = []
    for i in range(num):
        data = {'one': _rand(1000)}
        record = client.create_record(data=data)
        records.append(record['data'])
    return records


def _get_args():
    parser = argparse.ArgumentParser(description='End-to-end signing test')

    parser.add_argument('--auth', help='Basic Authentication',
                        type=str, default=DEFAULT_AUTH)

    parser.add_argument('--editor-auth', help='Basic Authentication for editor',
                        type=str, default=None)

    parser.add_argument('--reviewer-auth', help='Basic Authentication for reviewer',
                        type=str, default=None)

    parser.add_argument('--server', help='Kinto Server',
                        type=str, default=DEFAULT_SERVER)

    parser.add_argument('--source-bucket', help='Source bucket',
                        type=str, default=SOURCE_BUCKET)

    parser.add_argument('--source-col', help='Source collection',
                        type=str, default=SOURCE_COL)

    parser.add_argument('--reset', help='Reset collection data',
                        type=bool, default=False)

    return parser.parse_args()


def main():
    args = _get_args()

    client = Client(server_url=args.server, auth=tuple(args.auth.split(':')),
                    bucket=args.source_bucket,
                    collection=args.source_col)

    if args.editor_auth is None:
        args.editor_auth = args.auth

    if args.reviewer_auth is None:
        args.reviewer_auth = args.auth

    editor_client = Client(server_url=args.server,
                           auth=tuple(args.editor_auth.split(':')),
                           bucket=args.source_bucket,
                           collection=args.source_col)
    reviewer_client = Client(server_url=args.server,
                             auth=tuple(args.reviewer_auth.split(':')),
                             bucket=args.source_bucket,
                             collection=args.source_col)

    # 0. initialize source bucket/collection (if necessary)
    server_info = client.server_info()
    editor_id = editor_client.server_info()['user']['id']
    reviewer_id = reviewer_client.server_info()['user']['id']
    print('Server: {0}'.format(args.server))
    print('Author: {user[id]}'.format(**server_info))
    print('Editor: {0}'.format(editor_id))
    print('Reviewer: {0}'.format(reviewer_id))

    # 0. check that this collection is well configured.
    signer_capabilities = server_info['capabilities']['signer']
    to_review_enabled = signer_capabilities.get('to_review_enabled', False)
    group_check_enabled = signer_capabilities.get('group_check_enabled', False)

    resources = [r for r in signer_capabilities['resources']
                 if (args.source_bucket, args.source_col) == (r['source']['bucket'], r['source']['collection'])]
    assert len(resources) > 0, 'Specified source not configured to be signed'
    resource = resources[0]
    if to_review_enabled and 'preview' in resource:
        print('Signoff: {source[bucket]}/{source[collection]} => {preview[bucket]}/{preview[collection]} => {destination[bucket]}/{destination[collection]}'.format(**resource))
    else:
        print('Signoff: {source[bucket]}/{source[collection]} => {destination[bucket]}/{destination[collection]}'.format(**resource))
    print('Group check: {0}'.format(group_check_enabled))
    print('Review workflow: {0}'.format(to_review_enabled))

    print('_' * 80)

    bucket = client.create_bucket(if_not_exists=True)
    client.patch_bucket(permissions={'write': [editor_id, reviewer_id] + bucket['permissions']['write']},
                        if_match=bucket['data']['last_modified'], safe=True)

    client.create_collection(if_not_exists=True)

    if args.reset:
        client.delete_records()
        existing = 0
    else:
        existing_records = client.get_records()
        existing = len(existing_records)

    if group_check_enabled:
        editors_group = signer_capabilities['editors_group']
        client.create_group(id=editors_group, data={'members': [editor_id]}, if_not_exists=True)
        reviewers_group = signer_capabilities['reviewers_group']
        client.create_group(id=reviewers_group, data={'members': [reviewer_id]},
                            if_not_exists=True)

    dest_client = Client(server_url=args.server,
                         bucket=resource['destination']['bucket'],
                         collection=resource['destination']['collection'])

    preview_client = None
    if to_review_enabled and 'preview' in resource:
        preview_bucket = resource['preview']['bucket']
        preview_collection = resource['preview']['collection']
        preview_client = Client(server_url=args.server,
                                bucket=preview_bucket,
                                collection=preview_collection)

    # 1. upload data
    print('Author uploads 20 random records')
    records = upload_records(client, 20)

    # 2. ask for a signature
    # 2.1 ask for review (noop on old versions)
    print('Editor asks for review')
    data = {"status": "to-review"}
    editor_client.patch_collection(data=data)
    # 2.2 check the preview collection (if enabled)
    if preview_client:
        print('Check preview collection')
        preview_records = preview_client.get_records()
        expected = existing + 20
        assert len(preview_records) == expected, '%s != %s records' % (len(preview_records), expected)
        metadata = preview_client.get_collection()['data']
        preview_signature = metadata.get('signature')
        assert preview_signature, 'Preview collection not signed'
        preview_timestamp = collection_timestamp(preview_client)
    # 2.3 approve the review
    print('Reviewer approves and triggers signature')
    data = {"status": "to-sign"}
    reviewer_client.patch_collection(data=data)

    # 3. upload more data
    print('Author creates 20 others records')
    upload_records(client, 20)

    print('Editor updates 5 random records')
    for toupdate in random.sample(records, 5):
        editor_client.patch_record(data=dict(newkey=_rand(10), **toupdate))

    print('Author deletes 5 random records')
    for todelete in random.sample(records, 5):
        client.delete_record(id=todelete['id'])

    expected = existing + 20 + 20 - 5

    # 4. ask again for a signature
    # 2.1 ask for review (noop on old versions)
    print('Editor asks for review')
    data = {"status": "to-review"}
    editor_client.patch_collection(data=data)
    # 2.2 check the preview collection (if enabled)
    if preview_client:
        print('Check preview collection')
        preview_records = preview_client.get_records()
        assert len(preview_records) == expected, '%s != %s records' % (len(preview_records), expected)
        # Diff size is 20 + 5 if updated records are also all deleted,
        # or 30 if deletions and updates apply to different records.
        diff_since_last = preview_client.get_records(_since=preview_timestamp)
        assert 25 <= len(diff_since_last) <= 30, 'Changes since last signature are not consistent'

        metadata = preview_client.get_collection()['data']
        assert preview_signature != metadata['signature'], 'Preview collection not updated'

    # 2.3 approve the review
    print('Reviewer approves and triggers signature')
    data = {"status": "to-sign"}
    reviewer_client.patch_collection(data=data)

    # 5. wait for the result

    # 6. obtain the destination records and serialize canonically.

    records = list(dest_client.get_records())
    assert len(records) == expected, '%s != %s records' % (len(records), expected)
    timestamp = collection_timestamp(dest_client)
    serialized = canonical_json(records, timestamp)
    print('Hash is %r' % compute_hash(serialized))

    # 7. get back the signed hash

    dest_col = dest_client.get_collection()
    signature = dest_col['data']['signature']

    with open('pub', 'w') as f:
        f.write(signature['public_key'])

    # 8. verify the signature matches the hash
    signer = ECDSASigner(public_key='pub')
    try:
        signer.verify(serialized, signature)
        print('Signature OK')
    except Exception:
        print('Signature KO')
        raise


if __name__ == '__main__':
    main()
