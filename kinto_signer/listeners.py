import copy

from kinto.core import errors
from kinto.core.events import ACTIONS
from kinto.core.utils import instance_uri
from kinto.core.errors import ERRORS
from kinto.core.storage.exceptions import ObjectNotFoundError
from pyramid import httpexceptions
from pyramid.interfaces import IAuthorizationPolicy

from kinto_signer.updater import LocalUpdater, TRACKING_FIELDS
from kinto_signer import events as signer_events
from kinto_signer.utils import STATUS, PLUGIN_USERID, ensure_resource_exists


REVIEW_SETTINGS = ("reviewers_group", "editors_group", "to_review_enabled", "group_check_enabled")


def raise_invalid(**kwargs):
    kwargs.update(errno=ERRORS.INVALID_POSTED_DATA)
    raise errors.http_error(httpexceptions.HTTPBadRequest(), **kwargs)


def raise_forbidden(**kwargs):
    kwargs.update(errno=ERRORS.FORBIDDEN)
    raise errors.http_error(httpexceptions.HTTPForbidden(), **kwargs)


def pick_resource_and_signer(request, resources, bucket_id, collection_id):
    bucket_key = instance_uri(request, "bucket", id=bucket_id)
    collection_key = instance_uri(request, "collection", bucket_id=bucket_id, id=collection_id)

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

    if collection_key in request.registry.signers:
        signer = request.registry.signers[collection_key]
    elif bucket_key in request.registry.signers:
        signer = request.registry.signers[bucket_key]

    return resource, signer


def resource_group(resource, name, default):
    group = resource.get(name, default)
    # If review is configured per-bucket, the group patterns have to be replaced
    # with the source collection id.
    return group.format(collection_id=resource["source"]["collection"])


def sign_collection_data(event, resources, to_review_enabled, **kwargs):
    """
    Listen to resource change events, to check if a new signature is
    requested.

    When a source collection specified in settings is modified, and its
    new metadata ``status`` is set to ``"to-sign"``, then sign the data
    and update the destination.
    """
    payload = event.payload

    is_new_collection = payload["action"] == ACTIONS.CREATE.value

    current_user_id = event.request.prefixed_userid
    if current_user_id == PLUGIN_USERID:
        # Ignore changes made by plugin.
        return

    # Prevent recursivity, since the following operations will alter the current collection.
    impacted_objects = list(event.impacted_objects)

    for impacted in impacted_objects:
        new_collection = impacted["new"]
        old_collection = impacted.get("old", {})

        # Only sign the configured resources.
        resource, signer = pick_resource_and_signer(
            event.request,
            resources,
            bucket_id=payload["bucket_id"],
            collection_id=new_collection["id"],
        )
        if resource is None:
            continue

        updater = LocalUpdater(
            signer=signer,
            storage=event.request.registry.storage,
            permission=event.request.registry.permission,
            source=resource["source"],
            destination=resource["destination"],
        )

        uri = instance_uri(
            event.request, "collection", bucket_id=payload["bucket_id"], id=new_collection["id"]
        )

        has_review_enabled = "preview" in resource and resource.get(
            "to_review_enabled", to_review_enabled
        )

        payload = payload.copy()
        payload["uri"] = uri
        payload["collection_id"] = new_collection["id"]

        review_event_cls = None
        review_event_kw = dict(
            request=event.request,
            payload=payload,
            impacted_objects=[impacted],
            resource=resource,
            original_event=event,
        )

        new_status = new_collection.get("status")
        old_status = old_collection.get("status")

        # Autorize kinto-attachment metadata write access. #190
        event.request._attachment_auto_save = True

        if is_new_collection:
            if has_review_enabled:
                updater.destination = resource["preview"]
                updater.sign_and_update_destination(
                    event.request, source_attributes=new_collection, next_source_status=None
                )
            updater.destination = resource["destination"]
            updater.sign_and_update_destination(
                event.request, source_attributes=new_collection, next_source_status=None
            )

        if old_status == new_status:
            continue

        if new_status == STATUS.TO_SIGN:
            # Run signature process (will set `last_reviewer` field).
            updater.destination = resource["destination"]
            changes_count = updater.sign_and_update_destination(
                event.request, source_attributes=new_collection, previous_source_status=old_status
            )

            if old_status == STATUS.SIGNED:
                # When we refresh the signature, it is mainly in order to make sure that
                # the latest signer certificate was used. When a preview collection
                # is configured, we also want to refresh its signature.
                if has_review_enabled:
                    updater.destination = resource["preview"]
                    updater.sign_and_update_destination(
                        event.request,
                        source_attributes=new_collection,
                        previous_source_status=old_status,
                    )
            else:
                review_event_cls = signer_events.ReviewApproved
                review_event_kw["changes_count"] = changes_count

        elif new_status == STATUS.TO_REVIEW:
            if has_review_enabled:
                # If preview collection: update and sign preview collection
                updater.destination = resource["preview"]
                updater.sign_and_update_destination(
                    event.request,
                    source_attributes=new_collection,
                    next_source_status=STATUS.TO_REVIEW,
                )
            else:
                # If no preview collection: just track `last_editor`
                updater.update_source_review_request_by(event.request)
            review_event_cls = signer_events.ReviewRequested

        elif old_status == STATUS.TO_REVIEW and new_status == STATUS.WORK_IN_PROGRESS:
            review_event_cls = signer_events.ReviewRejected

        elif new_status == STATUS.TO_REFRESH:
            updater.refresh_signature(event.request, next_source_status=old_status)
            if has_review_enabled:
                updater.destination = resource["preview"]
                updater.refresh_signature(event.request, next_source_status=old_status)

        elif new_status == STATUS.TO_ROLLBACK:
            # Reset source with destination content, and set status to SIGNED.
            changes_count = updater.rollback_changes(event.request)
            if has_review_enabled:
                # Reset preview with destination content.
                updater.source = resource["preview"]
                changes_count += updater.rollback_changes(event.request, refresh_last_edit=False)
                # Refresh signature for this new preview collection content.
                updater.destination = resource["preview"]
                # Without refreshing the source attributes.
                updater.refresh_signature(event.request, next_source_status=None)
            # If some changes were effectively rolledback, send an event.
            if changes_count > 0:
                review_event_cls = signer_events.ReviewCanceled
                review_event_kw["changes_count"] = changes_count

        # Notify request of review.
        if review_event_cls:
            review_event = review_event_cls(**review_event_kw)
            event.request.bound_data.setdefault("kinto_signer.events", []).append(review_event)


def send_signer_events(event):
    """Send accumulated review events for this request. This listener is bound to the
    ``AfterResourceChanged`` event so that review events are sent only if the transaction
    was committed.
    """
    review_events = event.request.bound_data.pop("kinto_signer.events", [])
    for review_event in review_events:
        event.request.registry.notify(review_event)


def check_collection_status(
    event, resources, group_check_enabled, to_review_enabled, editors_group, reviewers_group
):
    """Make sure status changes are allowed.
    """
    payload = event.payload

    current_user_id = event.request.prefixed_userid
    if current_user_id == PLUGIN_USERID:
        # Ignore changes made by plugin.
        return

    user_principals = event.request.effective_principals

    for impacted in event.impacted_objects:
        old_collection = impacted.get("old", {})
        old_status = old_collection.get("status")
        new_collection = impacted["new"]
        new_status = new_collection.get("status")

        # Skip if collection is not configured for review.
        resource, _ = pick_resource_and_signer(
            event.request,
            resources,
            bucket_id=payload["bucket_id"],
            collection_id=new_collection["id"],
        )
        if resource is None:
            continue

        # to-review and group checking.
        _to_review_enabled = resource.get("to_review_enabled", to_review_enabled)
        _group_check_enabled = resource.get("group_check_enabled", group_check_enabled)
        _editors_group = resource_group(resource, "editors_group", default=editors_group)
        _reviewers_group = resource_group(resource, "reviewers_group", default=reviewers_group)
        # Member of groups have their URIs in their principals.
        editors_group_uri = instance_uri(
            event.request, "group", bucket_id=payload["bucket_id"], id=_editors_group
        )
        reviewers_group_uri = instance_uri(
            event.request, "group", bucket_id=payload["bucket_id"], id=_reviewers_group
        )

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
        # 3. signed -> to-sign
        elif new_status == STATUS.TO_SIGN:
            # Refresh signature (signed -> to-sign) does not require group membership
            if old_status == STATUS.SIGNED:
                continue

            # Only allow to-sign from to-review if reviewer and no-editor
            if reviewers_group_uri not in user_principals and _group_check_enabled:
                raise_forbidden(message="Not in %s group" % _reviewers_group)

            if old_status != STATUS.TO_REVIEW and _to_review_enabled:
                raise_invalid(message="Collection not reviewed")

            field_last_requester = TRACKING_FIELDS.LAST_REVIEW_REQUEST_BY.value
            is_same_editor = old_collection.get(field_last_requester) == current_user_id
            if _to_review_enabled and is_same_editor:
                raise_forbidden(message="Editor cannot review")

        # 4. to-sign -> signed
        elif new_status == STATUS.SIGNED:
            raise_invalid(message="Cannot set status to '%s'" % new_status)

        # 5. Refresh signature
        elif new_status == STATUS.TO_REFRESH:
            # Before here we would raise a 400 if the collection had never been
            # signed, but after some thought it does not really make sense.
            pass

        # Rollback changes
        elif new_status == STATUS.TO_ROLLBACK:
            if old_status == STATUS.SIGNED:
                raise_invalid(message="Collection has no work-in-progress")

        # Nobody can remove the status
        elif new_status is None:
            raise_invalid(message="Cannot remove status")
        # Unknown manual status
        else:
            raise_invalid(message="Invalid status '%s'" % new_status)


def prevent_collection_delete(event, resources):
    request = event.request
    bucket_id = event.payload["bucket_id"]
    for impacted in event.impacted_objects:
        collection_id = impacted["old"]["id"]

        in_used = None
        for resource in resources.values():
            destination = resource["destination"]
            if destination["bucket"] == bucket_id:
                if destination["collection"] is None or destination["collection"] == collection_id:
                    in_used = resource
            if "preview" in resource:
                preview = resource["preview"]
                if preview["bucket"] == bucket_id:
                    if preview["collection"] is None or preview["collection"] == collection_id:
                        in_used = resource
        if in_used:
            source_bucket_uri = instance_uri(
                event.request, "bucket", id=in_used["source"]["bucket"]
            )
            source_collection_id = in_used["source"]["collection"] or collection_id
            try:
                request.registry.storage.get(
                    resource_name="collection",
                    parent_id=source_bucket_uri,
                    object_id=source_collection_id,
                )
                raise_forbidden(message="Collection is in use.")
            except ObjectNotFoundError:
                # Do not prevent delete of preview/destination if source does not exist.
                pass


def check_collection_tracking(event, resources):
    """Make sure tracking fields are not changed manually/removed.
    """
    if event.request.prefixed_userid == PLUGIN_USERID:
        return

    for impacted in event.impacted_objects:
        old_collection = impacted.get("old", {})
        new_collection = impacted["new"]

        resource, _ = pick_resource_and_signer(
            event.request,
            resources,
            bucket_id=event.payload["bucket_id"],
            collection_id=new_collection["id"],
        )
        # Skip if resource is not configured.
        if resource is None:
            continue

        for field in TRACKING_FIELDS:
            old = old_collection.get(field.value)
            new = new_collection.get(field.value)
            if old != new:
                raise_invalid(message="Cannot change %r" % field)


def set_work_in_progress_status(event, resources):
    """Put the status in work-in-progress if was signed.
    """
    resource, signer = pick_resource_and_signer(
        event.request,
        resources,
        bucket_id=event.payload["bucket_id"],
        collection_id=event.payload["collection_id"],
    )
    # Skip if resource is not configured.
    if resource is None:
        return

    updater = LocalUpdater(
        signer=signer,
        storage=event.request.registry.storage,
        permission=event.request.registry.permission,
        source=resource["source"],
        destination=resource["destination"],
    )
    updater.update_source_status(STATUS.WORK_IN_PROGRESS, event.request)


def create_editors_reviewers_groups(event, resources, editors_group, reviewers_group):
    if event.request.prefixed_userid == PLUGIN_USERID:
        return

    bid = event.payload["bucket_id"]
    bucket_uri = instance_uri(event.request, "bucket", id=bid)

    current_user_id = event.request.prefixed_userid
    principals = event.request.prefixed_principals

    authz = event.request.registry.getUtility(IAuthorizationPolicy)

    for impacted in event.impacted_objects:
        new_collection = impacted["new"]

        # Skip if collection is not configured for review.
        resource, _ = pick_resource_and_signer(
            event.request,
            resources,
            bucket_id=event.payload["bucket_id"],
            collection_id=new_collection["id"],
        )
        if resource is None:
            continue

        _editors_group = resource_group(resource, "editors_group", default=editors_group)
        _reviewers_group = resource_group(resource, "reviewers_group", default=reviewers_group)

        required_perms = authz.get_bound_permissions(bucket_uri, "group:create")
        permission = event.request.registry.permission
        if not permission.check_permission(principals, required_perms):
            return

        group_perms = {"write": [current_user_id]}
        for group, members in ((_editors_group, [current_user_id]), (_reviewers_group, [])):
            ensure_resource_exists(
                request=event.request,
                resource_name="group",
                parent_id=bucket_uri,
                obj={"id": group, "members": members},
                permissions=group_perms,
                matchdict={"bucket_id": bid, "id": group},
            )

        # Allow those groups to write to the source collection.
        permission = event.request.registry.permission
        collection_uri = instance_uri(
            event.request, "collection", bucket_id=bid, id=resource["source"]["collection"]
        )
        for group in (_editors_group, _reviewers_group):
            group_principal = instance_uri(event.request, "group", bucket_id=bid, id=group)
            permission.add_principal_to_ace(collection_uri, "write", group_principal)


def cleanup_preview_destination(event, resources):
    storage = event.request.registry.storage

    for impacted in event.impacted_objects:
        old_collection = impacted["old"]

        resource, signer = pick_resource_and_signer(
            event.request,
            resources,
            bucket_id=event.payload["bucket_id"],
            collection_id=old_collection["id"],
        )
        if resource is None:
            continue

        for k in ("preview", "destination"):
            if k not in resource:  # pragma: nocover
                continue
            bid = resource[k]["bucket"]
            cid = resource[k]["collection"]
            collection_uri = instance_uri(event.request, "collection", bucket_id=bid, id=cid)
            storage.delete_all(resource_name="record", parent_id=collection_uri, with_deleted=True)

            updater = LocalUpdater(
                signer=signer,
                storage=storage,
                permission=event.request.registry.permission,
                source=resource["source"],
                destination=resource[k],
            )

            # At this point, the DELETE event was sent for the source collection,
            # but the source records may not have been deleted yet (it happens in an event
            # listener too). That's why we don't copy the records otherwise it will
            # recreate the records that were just deleted.
            updater.sign_and_update_destination(
                event.request,
                source_attributes=old_collection,
                next_source_status=None,
                push_records=False,
            )
