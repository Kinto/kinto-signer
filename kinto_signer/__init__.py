import pkg_resources
import functools

from kinto.core import errors
from kinto.core.events import ACTIONS, ResourceChanged
from kinto import logger
from pyramid import httpexceptions
from pyramid.exceptions import ConfigurationError

from kinto_signer.updater import LocalUpdater
from kinto_signer.signer import heartbeat
from kinto_signer import utils

#: Module version, as defined in PEP-0396.
__version__ = pkg_resources.get_distribution(__package__).version


def sign_collection_data(event, resources):
    """
    Listen to resource change events, to check if a new signature is
    requested.

    When a source collection specified in settings is modified, and its
    new metadata ``status`` is set to ``"to-sign"``, then sign the data
    and update the destination.
    """
    payload = event.payload

    if 'bucket_id' not in payload:
        # Safety check for kinto < 3.3 where events have incoherent payloads
        # on default bucket.
        return

    for impacted in event.impacted_records:
        new_collection = impacted['new']

        key = "/buckets/{bucket_id}/collections/{collection_id}".format(
            collection_id=new_collection['id'],
            bucket_id=payload['bucket_id'])

        resource = resources.get(key)

        # Only sign the configured resources.
        if resource is None:
            continue

        # Only sign when the new collection status is "to-sign".
        status = new_collection.get("status")
        if status != "to-sign":
            continue

        registry = event.request.registry
        updater = LocalUpdater(
            signer=registry.signers[key],
            storage=registry.storage,
            permission=registry.permission,
            source=resource['source'],
            destination=resource['destination'])

        try:
            updater.sign_and_update_destination(event.request)
        except Exception:
            logger.exception("Could not sign '{0}'".format(key))
            event.request.response.status = 503


def check_collection_status(event, resources):
    """Make sure status changes are allowed.
    """
    payload = event.payload

    if 'bucket_id' not in payload:
        # Safety check for kinto < 3.3 where events have incoherent payloads
        # on default bucket.
        return

    for impacted in event.impacted_records:
        old_collection = impacted.get("old", {}).copy()
        old_status = old_collection.get("status")
        new_collection = impacted["new"].copy()
        new_status = new_collection.get("status")

        key = "/buckets/{bucket_id}/collections/{collection_id}".format(
            bucket_id=payload["bucket_id"],
            collection_id=new_collection["id"])

        if key not in resources:
            continue

        if new_status not in (None, "to-sign", "to-review", "signed"):
            raise errors.http_error(httpexceptions.HTTPBadRequest(),
                                    message="Invalid status %r" % new_status)

        if new_status == "to-review":
            new_collection["last_promoter"] = event.request.prefixed_userid
            event.request.registry.storage.update(
                parent_id="/buckets/{bucket_id}".format(**payload),
                collection_id='collection',
                object_id=new_collection['id'],
                record=new_collection)
        elif new_status == "to-sign":
            new_collection["last_reviewer"] = event.request.prefixed_userid
            event.request.registry.storage.update(
                parent_id="/buckets/{bucket_id}".format(**payload),
                collection_id='collection',
                object_id=new_collection['id'],
                record=new_collection)

        # Nobody can change back to signed
        was_changed_to_signed = (new_status == "signed" and
                                 old_status != "signed")
        if was_changed_to_signed:
            raise errors.http_error(httpexceptions.HTTPForbidden(),
                                    message="Cannot set status to 'signed'")

        # Nobody can remove the status
        was_removed = (new_status is None and
                       old_status == "signed")
        if was_removed:
            raise errors.http_error(httpexceptions.HTTPForbidden(),
                                    message="Cannot remove status")

        # Only allow to-review from work-in-progress
        # Only allow to-sign from to-review if reviewer and no-editor


def set_work_in_progress_status(event, resources):
    """Put the status in work-in-progress if was signed.
    """
    payload = event.payload

    if 'bucket_id' not in payload:
        # Safety check for kinto < 3.3 where events have incoherent payloads
        # on default bucket.
        return

    key = "/buckets/{bucket_id}/collections/{collection_id}".format(**payload)
    resource = resources.get(key)
    if resource is None:
        return

    registry = event.request.registry
    updater = LocalUpdater(
        signer=registry.signers[key],
        storage=registry.storage,
        permission=registry.permission,
        source=resource['source'],
        destination=resource['destination'])
    updater.update_source_status("work-in-progress", event.request)


def _signer_dotted_location(settings, resource):
    """
    Returns the Python dotted location for the specified `resource`, along
    the associated settings prefix.

    If a ``signer_backend`` setting is defined for a particular bucket
    or a particular collection, then use the same prefix for every other
    settings names.

    .. note::

        This means that every signer settings must be duplicated for each
        dedicated signer.
    """
    backend_setting = 'signer_backend'
    prefix = 'signer.'
    bucket_wide = '{bucket}.'.format(**resource['source'])
    collection_wide = '{bucket}_{collection}.'.format(**resource['source'])
    if (prefix + collection_wide + backend_setting) in settings:
        prefix += collection_wide
    elif (prefix + bucket_wide + backend_setting) in settings:
        prefix += bucket_wide

    # Fallback to the local ECDSA signer.
    default_signer_module = "kinto_signer.signer.local_ecdsa"
    signer_dotted_location = settings.get(prefix + backend_setting,
                                          default_signer_module)
    return signer_dotted_location, prefix


def includeme(config):
    # Register heartbeat to check signer integration.
    config.registry.heartbeats['signer'] = heartbeat

    settings = config.get_settings()

    # Check source and destination resources are configured.
    raw_resources = settings.get('signer.resources')
    if raw_resources is None:
        error_msg = "Please specify the kinto.signer.resources setting."
        raise ConfigurationError(error_msg)
    resources = utils.parse_resources(raw_resources)

    # Load the signers associated to each resource.
    config.registry.signers = {}
    for key, resource in resources.items():
        dotted_location, prefix = _signer_dotted_location(settings, resource)
        signer_module = config.maybe_dotted(dotted_location)
        backend = signer_module.load_from_settings(settings, prefix)
        config.registry.signers[key] = backend

    # Expose the capabilities in the root endpoint.
    message = "Digital signatures for integrity and authenticity of records."
    docs = "https://github.com/Kinto/kinto-signer#kinto-signer"
    config.add_api_capability("signer", message, docs,
                              version=__version__,
                              resources=resources.values())

    config.add_subscriber(
        functools.partial(check_collection_status, resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',)
    )

    config.add_subscriber(
        functools.partial(set_work_in_progress_status, resources=resources),
        ResourceChanged,
        for_resources=('record',)
    )

    config.add_subscriber(
        functools.partial(sign_collection_data, resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',)
    )
