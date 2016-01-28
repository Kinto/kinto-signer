import os
import argparse
import json
from urlparse import urlparse
import logging

from kinto_client import Client
from kinto_client import exceptions
from kinto_signer import signer
from kinto_signer.hasher import compute_hash

logger = logging.getLogger(__name__)


class GatherRemoteChanges():
    def __init__(self, origin_settings, destination_settings, private_key,
                 cache_location='records.json'):
        self.origin = Client(**origin_settings)
        self.destination = Client(**destination_settings)
        self.signer = signer.ECDSABackend({'private_key': private_key})
        self.cache_location = cache_location
        self.cache = self.load_cache(self.cache_location)
        self.ensure_destination_exists()

    def ensure_destination_exists(self):
        # Will not create anything if it already exists, since safe=True is
        # passed.
        try:
            self.destination.create_bucket(safe=True)
        except exceptions.KintoException:
            pass
        try:
            self.destination.create_collection(safe=True)
        except exceptions.KintoException:
            pass

    def load_cache(self, cache_location):
        if os.path.exists(cache_location):
            with open(cache_location, 'r') as f:
                cache = json.load(f)
        else:
            cache = {
                'last_modified': 0,
                'records': {}
            }
        return cache

    def save_cache(self, cache=None, cache_location=None):
        cache = cache or self.cache
        cache_location = cache_location or self.cache_location
        with open(cache_location, 'wc') as f:
            json.dump(cache, f)

    def sync(self, since=None, should_sign=False):
        if since is None:
            since = self.cache['last_modified']
        records_diff, headers = self.origin.get_records(
            _since=since, if_none_match=since,  with_headers=True)
        # Apply the diff on the local cache.
        self.cache['records'].update({r['id']: r for r in records_diff})

        # Remove the deleted records from the cache.
        self.cache['records'] = {
            record_id: value
            for record_id, value in self.cache['records'].iteritems()
            if value.get('deleted', False) is not True
        }
        self.cache['last_modified'] = headers.get('ETag')

        if self.cache['records']:
            # Verify the signature of the local collection.
            collection_data = self.origin.get_collection()['data']
            signature = collection_data.get('signature')
            if signature:
                local_hash = compute_hash(self.cache['records'].values())
                self.signer.verify(local_hash, signature)

            # Update the local
            with self.destination.batch() as batch:
                for record in records_diff:
                    if record.get('deleted', False) is True:
                        batch.delete_record(
                            record['id'],
                            last_modified=record['last_modified'],
                            safe=False)
                    else:
                        batch.update_record(record, id=record['id'],
                                            safe=False)

            del collection_data['last_modified']
            if should_sign:
                collection_data['status'] = 'to-sign'
            # Should be part of the batch.
            self.destination.update_collection(data=collection_data)

        # finally, save the cache.
        self.save_cache()


def get_arguments():
    description = 'Load data from one kinto instance to another one.'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('origin_server',
                        help='The location of the origin server (with prefix)')
    parser.add_argument('destination_server',
                        help=('The location of the destination server '
                              '(with prefix)'))
    parser.add_argument('private_key', help=('The location of the private key '
                                             'to use for validation'))

    parser.add_argument('-s', '--sign', dest='should_sign',
                        action="store_true",
                        help='Ask the remote to sign the uploaded data.')

    # Auth: XXX improve later. For now only support Basic Auth.
    parser.add_argument('-a', '--auth', dest='auth',
                        help='Authentication, in the form "username:password"')

    # Defaults
    parser.add_argument('-v', '--verbose', action='store_const',
                        const=logging.INFO, dest='verbosity',
                        help='Show all messages.')

    parser.add_argument('-q', '--quiet', action='store_const',
                        const=logging.CRITICAL, dest='verbosity',
                        help='Show only critical errors.')

    parser.add_argument('-D', '--debug', action='store_const',
                        const=logging.DEBUG, dest='verbosity',
                        help='Show all messages, including debug messages.')
    return parser.parse_args()


def setup_logger(args):
    logger.addHandler(logging.StreamHandler())
    if args.verbosity:
        logger.setLevel(args.verbosity)


def get_server_settings(connection_string, auth=None):
    parsed = urlparse(connection_string)
    if parsed.username and parsed.password:
        auth = (parsed.username, parsed.password)

    path_parts = parsed.path.split('/')

    if len(path_parts) != 4:
        raise Exception("Please specify /version/buckets/collection in the "
                        "server URL, got %s" % parsed.path)
    _, version, bucket, collection = path_parts

    return {
        'server_url': '%s://%s/%s' % (parsed.scheme, parsed.netloc, version),
        'bucket': bucket,
        'collection': collection,
        'auth': auth
    }


def main():
    args = get_arguments()
    setup_logger(args)

    if args.auth is not None:
        auth = tuple(args.auth.split(':'))
    else:
        auth = None

    client = GatherRemoteChanges(
        origin_settings=get_server_settings(args.origin_server, auth),
        destination_settings=get_server_settings(
            args.destination_server,
            auth),
        private_key=args.private_key
    )
    client.sync(should_sign=args.should_sign)


if __name__ == "__main__":
    main()
