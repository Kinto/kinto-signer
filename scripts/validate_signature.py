import sys
from kinto_client import cli_utils
from kinto_signer.serializer import canonical_json
from kinto_signer.hasher import compute_hash
from kinto_signer.signer.local_ecdsa import ECDSASigner


DEFAULT_SERVER = "https://kinto.stage.mozaws.net/v1"
DEST_BUCKET = 'blocklists'
DEST_COLLECTION = 'certificates'


def main(args=None):
    parser = cli_utils.add_parser_options(
        description='Validate collection signature',
        default_server=DEFAULT_SERVER,
        default_bucket=DEST_BUCKET,
        default_collection=DEST_COLLECTION)

    args = parser.parse_args(args)

    client = cli_utils.create_client_from_args(args)

    # 1. Grab collection information
    dest_col = client.get_collection()

    # 2. Grab records
    records = client.get_records()

    # 3. Serialize
    serialized = canonical_json(records)

    # 3. Compute the hash
    computed_hash = compute_hash(serialized)

    # 4. Grab the signature
    signature = dest_col['data']['signature']

    # 5. Grab the public key
    with open('pub', 'w') as f:
        f.write(signature['public_key'])

    # 6. Verify the signature matches the hash
    signer = ECDSASigner(public_key='pub')
    try:
        signer.verify(serialized, signature)
        print('Signature OK')
    except Exception:
        print('Signature KO. Computed hash: %s' % computed_hash)
        raise

    # XXX 7. Verify that the public key is correct wrt the x5u chain


if __name__ == '__main__':
    main()
