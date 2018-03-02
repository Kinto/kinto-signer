import copy

import transaction
from kinto import logger
from kinto.core import errors
from kinto.core.utils import instance_uri
from kinto.core.errors import ERRORS
from pyramid import httpexceptions

from kinto_signer.updater import (LocalUpdater, FIELD_LAST_AUTHOR,
                                  FIELD_LAST_EDITOR, FIELD_LAST_REVIEWER)
from kinto_signer import events as signer_events
from kinto_signer.utils import STATUS


REVIEW_SETTINGS = ("reviewers_group", "editors_group",
                   "to_review_enabled", "group_check_enabled")

_PLUGIN_USERID = "plugin:kinto-signer"


def raise_invalid(**kwargs):
    # A ``400`` error response does not natively rollback the transaction.
    transaction.doom()
    kwargs.update(errno=ERRORS.INVALID_POSTED_DATA)
    raise errors.http_error(httpexceptions.HTTPBadRequest(), **kwargs)


def raise_forbidden(**kwargs):
    # A ``403`` error response does not natively rollback the transaction.
    transaction.doom()
    kwargs.update(errno=ERRORS.FORBIDDEN)
    raise errors.http_error(httpexceptions.HTTPForbidden(), **kwargs)


def pick_resource_and_signer(request, resources, bucket_id, collection_id):
    bucket_key = instance_uri(request, "bucket", id=bucket_id)
    collection_key = instance_uri(request, "collection",
                                  bucket_id=bucket_id,
                                  id=collection_id)

    settings = request.registry.settings

    resource = signer = None

    # Review might have been configured explictly for this collection,
    if collection_key in resources:
        resource = resources[collection_key]
    elif bucket_key in resources:
        # Or via its bucket.
        resource = copy.deepcopy(resources[bucket_key])
        # Since it was configured per bucket, we want to make this
        # resource look as if it was configured explicitly for this
        # collection.
        resource["source"]["collection"] = collection_id
        resource["destination"]["collection"] = collection_id
        if "preview" in resource:
            resource["preview"]["collection"] = collection_id

        # Look-up if a setting overrides a global one here.
        for setting in REVIEW_SETTINGS:
            setting_key = "signer.%s_%s.%s" % (bucket_id, collection_id, setting)
            if setting_key in settings:
                resource[setting] = settings[setting_key]

    if collection_key in request.registry.signers:
        signer = request.registry.signers[collection_key]
    elif bucket_key in request.registry.signers:
        signer = request.registry.signers[bucket_key]

    return resource, signer


def sign_collection_data(event, resources):
    """
    Listen to resource change events, to check if a new signature is
    requested.

    When a source collection specified in settings is modified, and its
    new metadata ``status`` is set to ``"to-sign"``, then sign the data
    and update the destination.
    """
    payload = event.payload

    current_user_id = event.request.prefixed_userid
    if current_user_id == _PLUGIN_USERID:
        # Ignore changes made by plugin.
        return

    # Prevent recursivity, since the following operations will alter the current collection.
    impacted_records = list(event.impacted_records)

    for impacted in impacted_records:
        new_collection = impacted['new']
        old_collection = impacted.get('old', {})

        # Only sign the configured resources.
        resource, signer = pick_resource_and_signer(event.request, resources,
                                                    bucket_id=payload['bucket_id'],
                                                    collection_id=new_collection['id'])
        if resource is None:
            continue

        updater = LocalUpdater(signer=signer,
                               storage=event.request.registry.storage,
                               permission=event.request.registry.permission,
                               source=resource['source'],
                               destination=resource['destination'])

        uri = instance_uri(event.request, "collection", bucket_id=payload['bucket_id'],
                           id=new_collection['id'])

        review_event_cls = None
        try:
            new_status = new_collection.get("status")
            old_status = old_collection.get("status")

            # Autorize kinto-attachment metadata write access. #190
            event.request._attachment_auto_save = True

            if new_status == STATUS.TO_SIGN:
                # Run signature process (will set `last_reviewer` field).
                updater.sign_and_update_destination(event.request, source=new_collection)
                if old_status != STATUS.SIGNED:
                    review_event_cls = signer_events.ReviewApproved

            elif new_status == STATUS.TO_REVIEW:
                if 'preview' in resource:
                    # If preview collection: update and sign preview collection
                    updater.destination = resource['preview']
                    updater.sign_and_update_destination(event.request,
                                                        source=new_collection,
                                                        next_source_status=STATUS.TO_REVIEW)
                else:
                    # If no preview collection: just track `last_editor`
                    with updater.send_events(event.request):
                        updater.update_source_editor(event.request)
                review_event_cls = signer_events.ReviewRequested

            elif old_status == STATUS.TO_REVIEW and new_status == STATUS.WORK_IN_PROGRESS:
                review_event_cls = signer_events.ReviewRejected

        except Exception:
            logger.exception("Could not sign '{0}'".format(uri))
            event.request.response.status = 503

        # Notify request of review.
        if review_event_cls:
            payload = payload.copy()
            payload["uri"] = uri
            payload["collection_id"] = new_collection['id']
            review_event = review_event_cls(request=event.request,
                                            payload=payload,
                                            impacted_records=[impacted],
                                            resource=resource,
                                            original_event=event)
            event.request.bound_data.setdefault('kinto_signer.events', []).append(review_event)


def send_signer_events(event):
    """Send accumulated review events for this request. This listener is bound to the
    ``AfterResourceChanged`` event so that review events are sent only if the transaction
    was committed.
    """
    review_events = event.request.bound_data.pop('kinto_signer.events', [])
    for review_event in review_events:
        event.request.registry.notify(review_event)


def check_collection_status(event, resources, group_check_enabled,
                            to_review_enabled, editors_group, reviewers_group):
    """Make sure status changes are allowed.
    """
    payload = event.payload

    current_user_id = event.request.prefixed_userid
    if current_user_id == _PLUGIN_USERID:
        # Ignore changes made by plugin.
        return

    user_principals = event.request.effective_principals

    for impacted in event.impacted_records:
        old_collection = impacted.get("old", {})
        old_status = old_collection.get("status")
        new_collection = impacted["new"]
        new_status = new_collection.get("status")

        # Skip if collection is not configured for review.
        resource, _ = pick_resource_and_signer(event.request, resources,
                                               bucket_id=payload["bucket_id"],
                                               collection_id=new_collection["id"])
        if resource is None:
            continue

        # to-review and group checking.
        _to_review_enabled = resource.get("to_review_enabled", to_review_enabled)
        _group_check_enabled = resource.get("group_check_enabled", group_check_enabled)
        _editors_group = resource.get("editors_group", editors_group)
        _reviewers_group = resource.get("reviewers_group", reviewers_group)
        # If review is configured per-bucket, the group patterns have to be replaced
        # with current collection.
        _editors_group = _editors_group.format(collection_id=resource["source"]["collection"])
        _reviewers_group = _reviewers_group.format(collection_id=resource["source"]["collection"])
        # Member of groups have their URIs in their principals.
        editors_group_uri = instance_uri(event.request, "group",
                                         bucket_id=payload["bucket_id"],
                                         id=_editors_group)
        reviewers_group_uri = instance_uri(event.request, "group",
                                           bucket_id=payload["bucket_id"],
                                           id=_reviewers_group)

        if old_status == new_status:
            continue

        # 1. None -> work-in-progress
        if new_status == STATUS.WORK_IN_PROGRESS:
            pass

        # 2. work-in-progress -> to-review
        elif new_status == STATUS.TO_REVIEW:
            if editors_group_uri not in user_principals and _group_check_enabled:
                raise_forbidden(message="Not in %s group" % _editors_group)

        # 3. to-review -> work-in-progress
        # 3. to-review -> to-sign
        elif new_status == STATUS.TO_SIGN:
            # Only allow to-sign from to-review if reviewer and no-editor
            if reviewers_group_uri not in user_principals and _group_check_enabled:
                raise_forbidden(message="Not in %s group" % _reviewers_group)

            requires_review = old_status not in (STATUS.TO_REVIEW,
                                                 STATUS.SIGNED)
            if requires_review and _to_review_enabled:
                raise_invalid(message="Collection not reviewed")

            is_same_editor = old_collection.get(FIELD_LAST_EDITOR) == current_user_id
            if _to_review_enabled and is_same_editor and old_status != STATUS.SIGNED:
                raise_forbidden(message="Editor cannot review")

        # 4. to-sign -> signed
        elif new_status == STATUS.SIGNED:
            raise_invalid(message="Cannot set status to '%s'" % new_status)

        # Nobody can remove the status
        elif new_status is None:
            raise_invalid(message="Cannot remove status")
        # Unknown manual status
        else:
            raise_invalid(message="Invalid status '%s'" % new_status)


def check_collection_tracking(event, resources):
    """Make sure tracking fields are not changed manually/removed.
    """
    if event.request.prefixed_userid == _PLUGIN_USERID:
        return

    tracking_fields = (FIELD_LAST_AUTHOR, FIELD_LAST_EDITOR, FIELD_LAST_REVIEWER)

    for impacted in event.impacted_records:
        old_collection = impacted.get("old", {})
        new_collection = impacted["new"]

        resource, _ = pick_resource_and_signer(event.request, resources,
                                               bucket_id=event.payload["bucket_id"],
                                               collection_id=new_collection["id"])
        # Skip if resource is not configured.
        if resource is None:
            continue

        for field in tracking_fields:
            old = old_collection.get(field)
            new = new_collection.get(field)
            if old != new:
                raise_invalid(message="Cannot change %r" % field)


def set_work_in_progress_status(event, resources):
    """Put the status in work-in-progress if was signed.
    """
    resource, signer = pick_resource_and_signer(event.request, resources,
                                                bucket_id=event.payload["bucket_id"],
                                                collection_id=event.payload["collection_id"])
    # Skip if resource is not configured.
    if resource is None:
        return

    updater = LocalUpdater(signer=signer,
                           storage=event.request.registry.storage,
                           permission=event.request.registry.permission,
                           source=resource['source'],
                           destination=resource['destination'])
    with updater.send_events(event.request):
        updater.update_source_status(STATUS.WORK_IN_PROGRESS, event.request)
