from cliquet.events import ResourceChanged

from kinto_signer import utils
from kinto_signer.updater import LocalUpdater


def load_signer(config, bucket, collection):
    """Loads a signer instance for the specified bucket and collection.

    :param bucket:
        The source bucket for which the signer should be loaded.

    :param collection:
        The source collection for which the signer should be loaded.

    :param settings:
        A python dict where to look for configuration keys.
    """
    settings = config.get_settings()
    default_signer_module = "kinto_signer.signer.local_ecdsa"
    signer_location = utils.get_setting(
        settings, 'signer_backend', bucket, collection,
        default=default_signer_module)
    signer_module = config.maybe_dotted(signer_location)
    return signer_module.load_from_settings(settings)


def includeme(config):
    settings = config.get_settings()

    # Check source and destination resources are configured.
    raw_resources = settings.get('signer.resources')
    if raw_resources is None:
        raise ValueError("Please specify the kinto_signer.resources value.")
    available_resources = utils.parse_resources(raw_resources)

    # Expose the capabilities in the root endpoint.
    message = "Provide signing capabilities to the server."
    docs = "https://github.com/Kinto/kinto-signer#kinto-signer"
    resources = sorted(available_resources.keys())
    config.add_api_capability("signer", message, docs,
                              resources=resources)

    # Listen to resource change events, to check if a new signature is
    # requested.
    def on_resource_changed(event):
        payload = event.payload
        requested_resource = "{bucket_id}/{collection_id}".format(**payload)
        if requested_resource not in available_resources:
            return  # Only sign the configured resources.

        resource = available_resources.get(requested_resource)
        should_sign = any([True for r in event.impacted_records
                           if r['new'].get('status') == 'to-sign'])
        if not should_sign:
            return  # Only sign when the new collection status is "to-sign".

        signer = load_signer(
            config=config,
            bucket=resource['source']['bucket'],
            collection=resource['source']['collection'])

        registry = event.request.registry
        updater = LocalUpdater(
            signer=signer,
            storage=registry.storage,
            permission=registry.permission,
            source=resource['source'],
            destination=resource['destination'])

        updater.sign_and_update_remote()

    config.add_subscriber(
        on_resource_changed,
        ResourceChanged,
        for_actions=('create', 'update'),
        for_resources=('collection',)
    )
