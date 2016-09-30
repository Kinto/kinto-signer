import random
from string import hexdigits
import argparse

from kinto_http import Client, exceptions as kinto_exceptions
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
        record = client.create_record(data)
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
    print('Server: {0}'.format(args.server))
    print('Author: {user[id]}'.format(**client.server_info()))
    print('Editor: {user[id]}'.format(**editor_client.server_info()))
    print('Reviewer: {user[id]}'.format(**reviewer_client.server_info()))
    try:
        client.delete_collection()
    except kinto_exceptions.KintoException:
        pass
    client.create_bucket(if_not_exists=True)
    client.create_collection(if_not_exists=True)

    # 0. check that this collection is well configured.
    signer_capabilities = server_info['capabilities']['signer']
    to_review_enabled = signer_capabilities.get('to_review_enabled', False)
    resources = [r for r in signer_capabilities['resources']
                 if (args.source_bucket, args.source_col) == (r['source']['bucket'], r['source']['collection'])]
    assert len(resources) > 0, 'Specified source not configured to be signed'
    resource = resources[0]
    if to_review_enabled and 'preview' in resource:
        print('Signoff: {source[bucket]}/{source[collection]} => {preview[bucket]}/{preview[collection]} => {destination[bucket]}/{destination[collection]}'.format(**resource))
    else:
        print('Signoff: {source[bucket]}/{source[collection]} => {destination[bucket]}/{destination[collection]}'.format(**resource))
    if signer_capabilities.get('group_check_enabled', False):
        print('/!\ Group check is enabled.')
    if to_review_enabled:
        print('/!\ Review workflow is enabled.')

    print('_' * 80)

    # 1. upload data
    print('Uploading 20 random records')
    records = upload_records(client, 20)

    # 2. ask for a signature by toggling "to-sign"
    print('Trigger signature')
    data = {"status": "to-sign"}
    client.patch_collection(data=data)

    # 3. upload more data
    print('Create 20 others records')
    upload_records(client, 20)

    print('Update 5 random records')
    for toupdate in random.sample(records, 5):
        client.patch_record(dict(newkey=_rand(10), **toupdate))

    print('Delete 5 random records')
    for todelete in random.sample(records, 5):
        client.delete_record(todelete['id'])

    # 4. ask again for a signature by toggling "to-sign"
    print('Trigger signature')
    data = {"status": "to-sign"}
    client.patch_collection(data=data)

    # 5. wait for the result

    # 6. obtain the destination records and serialize canonically.

    dest_client = Client(server_url=args.server, bucket=args.dest_bucket,
                         collection=args.dest_col)

    records = dest_client.get_records()
    assert len(records) == 35, "%s != 35 records" % len(records)
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
