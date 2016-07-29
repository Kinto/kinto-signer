import pkg_resources
import functools

import transaction
from kinto.core import errors
from kinto.core.initialization import load_default_settings
from kinto.core.events import ACTIONS, ResourceChanged
from kinto import logger
from pyramid import httpexceptions
from pyramid.exceptions import ConfigurationError

from kinto_signer.updater import LocalUpdater
from kinto_signer.signer import heartbeat
from kinto_signer import utils

#: Module version, as defined in PEP-0396.
__version__ = pkg_resources.get_distribution(__package__).version


DEFAULT_SETTINGS = {
    'signer.force_review': 'false',
    'signer.force_groups': 'true',
}


def raise_invalid(**kwargs):
    # We are obliged to abort explicitly because 4XX errors don't rollback
    # transactions. See https://github.com/Kinto/kinto/issues/624
    # Note: this only works with PostgreSQL backend since other don't
    # implement "per-request" transactions.
    transaction.abort()
    raise errors.http_error(httpexceptions.HTTPBadRequest(), **kwargs)


def raise_forbidden(**kwargs):
    transaction.abort()
    raise errors.http_error(httpexceptions.HTTPForbidden(), **kwargs)


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

        new_status = new_collection.get("status")

        registry = event.request.registry
        updater = LocalUpdater(
            signer=registry.signers[key],
            storage=registry.storage,
            permission=registry.permission,
            source=resource['source'],
            destination=resource['destination'])

        # Only sign when the new collection status is "to-sign".
        if new_status == "to-sign":
            try:
                updater.sign_and_update_destination(event.request)
            except Exception:
                logger.exception("Could not sign '{0}'".format(key))
                event.request.response.status = 503

        elif new_status == "to-review":
            if "last_promoter" not in new_collection:  # recursivity.
                updater.update_source_promoter(event.request)


def check_collection_status(event, resources, force_review, force_groups):
    """Make sure status changes are allowed.
    """
    payload = event.payload

    if 'bucket_id' not in payload:
        # Safety check for kinto < 3.3 where events have incoherent payloads
        # on default bucket.
        return

    promoters_group = "/buckets/{bucket_id}/groups/promoters".format(**payload)
    reviewers_group = "/buckets/{bucket_id}/groups/reviewers".format(**payload)
    current_user_id = event.request.prefixed_userid
    current_principals = event.request.effective_principals

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
            raise_invalid(message="Invalid status %r" % new_status)

        if old_status == new_status:
            continue

        # Only allow to-sign from to-review if reviewer and no-editor
        if new_status == "to-sign":
            if reviewers_group not in current_principals and force_groups:
                raise_forbidden(message="Not in reviewers group")

            if old_status not in ("to-review", "signed") and force_review:
                raise_forbidden(message="Collection not reviewed")

            if old_collection.get("last_promoter") == current_user_id:
                raise_forbidden(message="Promoter cannot review")

        elif new_status == "to-review":
            if promoters_group not in current_principals and force_groups:
                raise_forbidden(message="Not in promoters group")

        elif new_status is None and old_status is not None:
            # Nobody can remove the status
            raise_forbidden(message="Cannot remove status")

        elif new_status == "signed":
            # Nobody can set to signed
            raise_forbidden(message="Cannot set status to 'signed'")


def check_collection_tracking(event, resources):
    """Make tracking fields are not changed manually/removed.

    XXX: Use readonly field notion from kinto.core ?
    """
    payload = event.payload

    if 'bucket_id' not in payload:
        # Safety check for kinto < 3.3 where events have incoherent payloads
        # on default bucket.
        return

    tracking_fields = ("last_editor", "last_promoter", "last_reviewer")

    for impacted in event.impacted_records:
        old_collection = impacted.get("old", {})
        new_collection = impacted["new"]

        for field in tracking_fields:
            old = old_collection.get(field)
            new = new_collection.get(field)
            if old != new:
                raise_forbidden(message="Cannot change %r" % field)


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

    load_default_settings(config, DEFAULT_SETTINGS)

    force_review = settings["signer.force_review"]
    force_groups = settings["signer.force_groups"]

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
        functools.partial(set_work_in_progress_status, resources=resources),
        ResourceChanged,
        for_resources=('record',)
    )

    config.add_subscriber(
        functools.partial(check_collection_status, resources=resources,
                          force_review=force_review, force_groups=force_groups),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',)
    )

    config.add_subscriber(
        functools.partial(check_collection_tracking, resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',)
    )

    config.add_subscriber(
        functools.partial(sign_collection_data, resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',)
    )
