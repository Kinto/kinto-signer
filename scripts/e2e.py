import random
from string import hexdigits
import argparse
from functools import partial

from kinto_client import Client
from kinto_signer.serializer import canonical_json
from kinto_signer.hasher import compute_hash
from kinto_signer.signer.local_ecdsa import ECDSASigner


DEFAULT_SERVER = "http://some:guy@localhost:8888/v1"
SOURCE_BUCKET = 'source'
DEST_BUCKET = 'destination'
SOURCE_COL = 'collection1'
DEST_COL = 'collection1'


def _rand(size=10):
    return ''.join([random.choice(hexdigits) for _ in range(size)])


def upload_records(client, num=100):
    bucket_name = SOURCE_BUCKET
    collection_name = SOURCE_COL

    client.delete_collection(bucket=bucket_name, collection=collection_name)

    client.create_bucket(bucket=bucket_name, if_not_exists=True)
    client.create_collection(bucket=bucket_name, collection=collection_name,
                             if_not_exists=True)

    records = []

    for i in range(num):
        data = {'one': _rand(1000)}
        res = client.create_record(data, bucket=bucket_name,
                                   collection=collection_name)
        records.append(res['data'])

    serialized = canonical_json(records)

    res = {'bucket': bucket_name,
           'collection': collection_name,
           'records': records,
           'hash': compute_hash(serialized),
           'payload': serialized}

    return res


def _get_args():
    parser = argparse.ArgumentParser(description='End-to-end signing test')

    parser.add_argument('--auth', help='Basic Authentication',
                        type=str, default='some:guy')

    parser.add_argument('--server', help='Kinto Server',
                        type=str, default='http://localhost:8888/v1')

    parser.add_argument('--source-bucket', help='Source bucket',
                        type=str, default=SOURCE_BUCKET)

    parser.add_argument('--dest-bucket', help='Destination bucket',
                        type=str, default=DEST_BUCKET)

    parser.add_argument('--source-col', help='Source collection',
                        type=str, default=SOURCE_COL)

    parser.add_argument('--dest-col', help='Destination collection',
                        type=str, default=DEST_COL)

    return parser.parse_args()


def main():
    args = _get_args()

    # why do I have to do all of this just to set up auth...
    def _auth(req, user='', password=''):
        req.prepare_auth((user, password))
        return req

    if args.auth is not None:
        user, password = args.auth.split(':')
        args.auth = partial(_auth, user=user, password=password)

    client = Client(server_url=args.server, auth=args.auth)

    # 1. upload data
    print('Uploading 100 random records')
    res = upload_records(client, 100)
    print('Hash is %r' % res['hash'])

    # 2. ask for a signature by toggling "to-sign"
    data = {"status": "to-sign"}
    client.patch_collection(data=data, bucket=res['bucket'],
                            collection=res['collection'])

    # 3. wait for the result

    # 4. get back the signed hash
    dest_col = client.get_collection(bucket=DEST_BUCKET,
                                     collection=DEST_COL)

    signature = dest_col['data']['signature']

    with open('pub', 'w') as f:
        f.write(signature['public_key'])

    # 5. verify the signature matches the hash
    signer = ECDSASigner(public_key='pub')
    try:
        signer.verify(res['payload'], signature)
        print('Signature OK')
    except Exception:
        print('Signature KO')
        raise


if __name__ == '__main__':
    main()
