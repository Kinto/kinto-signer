from pyramid.settings import aslist
from cliquet.events import ResourceChanged

from kinto_signer import signer as signer_module
from kinto_signer.updater import LocalUpdater


def parse_resources(raw_resources, settings):
    resources = {}
    for res in aslist(raw_resources):
        if ";" not in res:
            msg = ("Resources should be defined as "
                   "'bucket/coll;bucket/coll'. Got %r" % res)
            raise ValueError(msg)
        source, destination = res.split(';')

        def _get_resource(resource):
            parts = resource.split('/')
            if len(parts) != 2:
                msg = ("Resources should be defined as bucket/collection. "
                       "Got %r" % resource)
                raise ValueError(msg)
            return {
                'bucket': parts[0],
                'collection': parts[1]
            }

        resources[source] = {
            'source': _get_resource(source),
            'destination': _get_resource(destination),
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
        print(event, event.payload, event.impacted_records)
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
            updater = LocalUpdater(
                signer=registry.signer,
                storage=registry.storage,
                source=resource['source'],
                destination=resource['destination'])

            updater.sign_and_update_remote()

    config.add_subscriber(
        on_resource_changed,
        ResourceChanged,
        for_actions=('create', 'update'),
        for_resources=('collection',)
    )
