import functools

from cliquet.events import ACTIONS, ResourceChanged
from pyramid.exceptions import ConfigurationError

from kinto_signer import utils
from kinto_signer.updater import LocalUpdater


def on_collection_changed(resources, event):
    """
    Listen to resource change events, to check if a new signature is
    requested.

    When a source collection specified in settings is modified, and its
    new metadata ``status`` is set to ``"to-sign"``, then sign the data
    and update the destination.
    """
    payload = event.payload
    requested_resource = "{bucket_id}/{collection_id}".format(**payload)
    if requested_resource not in resources:
        return  # Only sign the configured resources.

    resource = resources.get(requested_resource)
    should_sign = any([True for r in event.impacted_records
                       if r['new'].get('status') == 'to-sign'])
    if not should_sign:
        return  # Only sign when the new collection status is "to-sign".

    registry = event.request.registry
    updater = LocalUpdater(
        signer=registry.signer,
        storage=registry.storage,
        permission=registry.permission,
        source=resource['source'],
        destination=resource['destination'])

    updater.sign_and_update_remote()


def includeme(config):
    settings = config.get_settings()

    # Load the signer from its dotted location. Fallback to the local ECDSA
    # signer.
    default_signer_module = "kinto_signer.signer.local_ecdsa"
    signer_dotted_location = settings.get(
        'signer.signer_backend', default_signer_module)
    signer_module = config.maybe_dotted(signer_dotted_location)
    config.registry.signer = signer_module.load_from_settings(settings)

    # Check source and destination resources are configured.
    raw_resources = settings.get('signer.resources')
    if raw_resources is None:
        error_msg = "Please specify the kinto_signer.resources value."
        raise ConfigurationError(error_msg)
    resources = utils.parse_resources(raw_resources)

    # Expose the capabilities in the root endpoint.
    message = "Provide signing capabilities to the server."
    docs = "https://github.com/Kinto/kinto-signer#kinto-signer"
    config.add_api_capability("signer", message, docs,
                              resources=sorted(resources.keys()))

    config.add_subscriber(
        functools.partial(on_collection_changed, resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',)
    )
