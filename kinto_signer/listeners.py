import transaction
from kinto.core import errors

from kinto import logger
from pyramid import httpexceptions

from kinto_signer.updater import LocalUpdater
from kinto_signer.utils import STATUS


def raise_invalid(**kwargs):
    # A ``400`` error response does not natively rollback the transaction.
    transaction.doom()
    raise errors.http_error(httpexceptions.HTTPBadRequest(), **kwargs)


def raise_forbidden(**kwargs):
    # A ``403`` error response does not natively rollback the transaction.
    transaction.doom()
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

    for impacted in event.impacted_records:
        new_collection = impacted['new']

        key = "/buckets/{bucket_id}/collections/{collection_id}".format(
            collection_id=new_collection['id'],
            bucket_id=payload['bucket_id'])

        resource = resources.get(key)

        # Only sign the configured resources.
        if resource is None:
            continue

        registry = event.request.registry
        updater = LocalUpdater(signer=registry.signers[key],
                               storage=registry.storage,
                               permission=registry.permission,
                               source=resource['source'],
                               destination=resource['destination'])

        new_status = new_collection.get("status")
        if new_status == STATUS.TO_SIGN:
            # Run signature process (will set `last_reviewer` field).
            try:
                updater.sign_and_update_destination(event.request)
            except Exception:
                logger.exception("Could not sign '{0}'".format(key))
                event.request.response.status = 503

        elif new_status == STATUS.TO_REVIEW:
            # Track `last_editor`
            updater.update_source_editor(event.request)


def check_collection_status(event, resources, force_groups, force_review,
                            editors_group, reviewers_group):
    """Make sure status changes are allowed.
    """
    payload = event.payload

    editors_group = "/buckets/{bucket_id}/groups/{group_name}".format(
        group_name=editors_group, **payload)
    reviewers_group = "/buckets/{bucket_id}/groups/{group_name}".format(
        group_name=reviewers_group, **payload)

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

        # Skip if resource is not configured.
        if key not in resources:
            continue

        if old_status == new_status:
            continue

        # Only these status can be set manually.
        if new_status in (STATUS.SIGNED,):
            raise_invalid(message="Cannot set status to '%s'" % new_status)

        # 1. None -> work-in-progress
        # 2. work-in-progress -> to-review
        elif new_status == STATUS.TO_REVIEW:
            if editors_group not in current_principals and force_groups:
                raise_forbidden(message="Not in editors group")

        # 3. to-review -> work-in-progress
        elif new_status == STATUS.WORK_IN_PROGRESS:
            pass

        # 3. to-review -> to-sign
        elif new_status == STATUS.TO_SIGN:
            # Only allow to-sign from to-review if reviewer and no-editor
            if reviewers_group not in current_principals and force_groups:
                raise_forbidden(message="Not in reviewers group")

            requires_review = old_status not in (STATUS.TO_REVIEW,
                                                 STATUS.SIGNED)
            if requires_review and force_review:
                raise_invalid(message="Collection not reviewed")

            if old_collection.get("last_editor") == current_user_id:
                raise_forbidden(message="Editor cannot review")

        # 4. to-sign -> signed

        # Nobody can remove the status
        elif new_status is None:
            raise_invalid(message="Cannot remove status")
        # Unknown manual status
        else:
            raise_invalid(message="Invalid status '%s'" % new_status)


def check_collection_tracking(event, resources):
    """Make sure tracking fields are not changed manually/removed.
    """
    tracking_fields = ("last_author", "last_editor", "last_reviewer")

    for impacted in event.impacted_records:
        old_collection = impacted.get("old", {})
        new_collection = impacted["new"]

        # Skip if resource is not configured.
        key = "/buckets/{bucket_id}/collections/{collection_id}".format(
            collection_id=new_collection['id'],
            bucket_id=event.payload['bucket_id'])
        if key not in resources:
            continue

        for field in tracking_fields:
            old = old_collection.get(field)
            new = new_collection.get(field)
            if old != new:
                raise_invalid(message="Cannot change %r" % field)


def set_work_in_progress_status(event, resources):
    """Put the status in work-in-progress if was signed.
    """
    payload = event.payload

    key = "/buckets/{bucket_id}/collections/{collection_id}".format(**payload)
    resource = resources.get(key)
    if resource is None:
        return

    registry = event.request.registry
    updater = LocalUpdater(signer=registry.signers[key],
                           storage=registry.storage,
                           permission=registry.permission,
                           source=resource['source'],
                           destination=resource['destination'])
    updater.update_source_status(STATUS.WORK_IN_PROGRESS, event.request)
