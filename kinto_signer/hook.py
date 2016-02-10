from urlparse import urlparse
from pyramid.settings import aslist
from cliquet.events import ResourceChanged

from kinto_signer import signer as signer_module
from kinto_signer.updater import RemoteUpdater
import kinto_client


def get_server_settings(connection_string, auth=None, **kwargs):
    if connection_string != "local":
        parsed = urlparse(connection_string)
        if parsed.username and parsed.password:
            auth = (parsed.username, parsed.password)

        path_parts = parsed.path.split('/')

        if len(path_parts) != 2:
            raise Exception("Please specify scheme://server/version in the "
                            "server URL, got %s" % parsed.path)
        _, version = path_parts
        server_url = '%s://%s/%s' % (parsed.scheme, parsed.netloc, version)
    else:
        server_url = "local"

    kwargs.update({
        'server_url': server_url,
        'auth': auth
    })
    return kwargs


def parse_resources(raw_resources, settings):
    resources = {}
    for res in aslist(raw_resources):
        if ";" not in res:
            msg = ("Resources should be defined as "
                   "'local:bucket/coll;remote:bucket/coll'. Got %r" % res)
            raise ValueError(msg)
        local, remote = res.split(';')
        if not local.startswith('local:'):
            msg = ("Only local resources can trigger signatures. "
                   "They should start with 'local:'. Got %r" % local)
            raise ValueError(msg)

        _, local_resource_id = local.split(':', 1)

        remote_alias, remote_resource_id = remote.split(':', 1)

        if remote_alias == 'local':
            remote_server_url = 'local'
        else:
            remote_alias_setting = 'kinto_signer.%s' % remote_alias
            if remote_alias_setting not in settings:
                msg = ("The remote alias you specified is not defined. "
                       "Check for %s" % remote_alias_setting)
                raise ValueError(msg)
            remote_server_url = settings[remote_alias_setting]

        remote_bucket_id, remote_collection_id = remote_resource_id.split('/')
        local_bucket_id, local_collection_id = local_resource_id.split('/')

        remote_settings = get_server_settings(
            remote_server_url,
            collection=remote_collection_id,
            bucket=remote_bucket_id
        )

        resources[local_resource_id] = {
            'remote': remote_settings,
            'local': {
                'bucket': remote_bucket_id,
                'collection': remote_collection_id
            }
        }
        return resources


def includeme(config):
    # Process settings to remove storage wording.
    settings = config.get_settings()

    priv_key = settings.get('kinto_signer.private_key')
    config.registry.signer = signer_module.ECDSABackend(
        {'private_key': priv_key})

    raw_resources = settings.get('kinto_signer.resources')
    if raw_resources is None:
        raise ValueError("Please specify the kinto_signer.resources value.")
    available_resources = parse_resources(raw_resources, settings)

    message = "Provide signing capabilities to the server."
    docs = "https://github.com/mozilla-services/kinto-signer#kinto-signer"
    config.add_api_capability("signer", message, docs,
                              resources=available_resources.keys())

    def on_resource_changed(event):
        payload = event.payload
        requested_resource = "{bucket_id}/{collection_id}".format(**payload)
        if requested_resource not in available_resources:
            return

        resource = available_resources.get(requested_resource)

        should_sign = any([True for r in event.impacted_records
                           if r['new'].get('status') == 'to-sign'])
        if should_sign:
            registry = event.request.registry
            # XXX Add Auth.
            remote = kinto_client.Client(**resource['remote'])
            updater = RemoteUpdater(
                remote=remote,
                signer=registry.signer,
                storage=registry.storage,
                local_bucket=resource['local']['bucket'],
                local_collection=resource['local']['collection'])

            updater.sign_and_update_remote()

    config.add_subscriber(
        on_resource_changed,
        ResourceChanged,
        for_actions=('create', 'update'),
        for_resources=('collection',)
    )
