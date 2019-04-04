import datetime
import logging
import uuid
from enum import Enum

from kinto.core.events import ACTIONS
from kinto.core.storage import Filter, Sort
from kinto.core.storage.exceptions import RecordNotFoundError
from kinto.core.utils import COMPARISON
from pyramid.security import Everyone
from pyramid.settings import aslist

from kinto_signer.serializer import canonical_json
from kinto_signer.utils import (STATUS, ensure_resource_exists,
                                notify_resource_event)

try:
    import boto3
except ImportError:  # pragma: nocover
    boto3 = None

logger = logging.getLogger(__name__)


FIELD_ID = 'id'
FIELD_LAST_MODIFIED = 'last_modified'


class TRACKING_FIELDS(Enum):
    LAST_EDIT_BY = 'last_edit_by'
    LAST_EDIT_DATE = 'last_edit_date'
    LAST_REVIEW_REQUEST_BY = 'last_review_request_by'
    LAST_REVIEW_REQUEST_DATE = 'last_review_request_date'
    LAST_REVIEW_BY = 'last_review_by'
    LAST_REVIEW_DATE = 'last_review_date'
    LAST_SIGNATURE_BY = 'last_signature_by'
    LAST_SIGNATURE_DATE = 'last_signature_date'


def _ensure_resource(resource):
    if not set(resource.keys()).issuperset({'bucket', 'collection'}):
        msg = "Resources should contain both bucket and collection"
        raise ValueError(msg)
    return resource


class LocalUpdater(object):
    """Sign items in the source and push them to the destination.

    Triggers a signature of all records in the source destination, and
    eventually update the destination with the new signature and the updated
    records.

    :param source:
        Python dictionary containing the bucket and collection of the source.

    :param destination:
        Python dictionary containing the bucket and collection of the
        destination.

    :param signer:
        The instance of the signer that will be used to generate the signature
        on the collection.

    :param storage:
        The instance of kinto.core.storage that will be used to retrieve
        records from the source and add new items to the destination.
    """

    def __init__(self, source, destination, signer, storage, permission):
        self._source = None
        self._destination = None

        self.source = source
        self.destination = destination
        self.signer = signer
        self.storage = storage
        self.permission = permission

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, source):
        self._source = _ensure_resource(source)
        self.source_bucket_uri = '/buckets/%s' % source['bucket']
        self.source_collection_uri = '/buckets/%s/collections/%s' % (
            source['bucket'],
            source['collection'])

    @property
    def destination(self):
        return self._destination

    @destination.setter
    def destination(self, destination):
        self._destination = _ensure_resource(destination)
        self.destination_bucket_uri = '/buckets/%s' % (
            self.destination['bucket'])
        self.destination_collection_uri = '/buckets/%s/collections/%s' % (
            self.destination['bucket'],
            self.destination['collection'])

    def sign_and_update_destination(self, request, source_attributes,
                                    next_source_status=STATUS.SIGNED,
                                    previous_source_status=None,
                                    push_records=True):
        """Sign the specified collection.

        0. Create the destination bucket / collection
        1. Get all the records of the collection
        2. Send all records since the last_modified of the destination
        3. Compute a hash of these records
        4. Ask the signer for a signature
        5. Send the signature to the destination.
        """
        self.create_destination(request)

        if push_records:
            self.push_records_to_destination(request)

        records, timestamp = self.get_destination_records(empty_none=False)
        serialized_records = canonical_json(records, timestamp)
        logger.debug("{}:\t'{}'".format(self.source_collection_uri, serialized_records))
        signature = self.signer.sign(serialized_records)

        self.set_destination_signature(signature, source_attributes, request)
        if next_source_status is not None:
            self.update_source_status(next_source_status, request, previous_source_status)

        self.invalidate_cloudfront_cache(request, timestamp)

    def refresh_signature(self, request, next_source_status):
        """Refresh the signature without moving records.
        """
        records, timestamp = self.get_destination_records(empty_none=False)
        serialized_records = canonical_json(records, timestamp)
        logger.debug("{}:\t'{}'".format(self.source_collection_uri, serialized_records))
        signature = self.signer.sign(serialized_records)
        self.set_destination_signature(signature, request=request, source_attributes={})

        current_userid = request.prefixed_userid
        current_date = datetime.datetime.now(datetime.timezone.utc).isoformat()
        attrs = {'status': next_source_status}
        attrs[TRACKING_FIELDS.LAST_SIGNATURE_BY.value] = current_userid
        attrs[TRACKING_FIELDS.LAST_SIGNATURE_DATE.value] = current_date
        self._update_source_attributes(request, **attrs)

    def create_destination(self, request):
        """Create the destination bucket/collection if they don't already exist.
        """
        # With the current implementation, the destination is not writable by
        # anyone and readable by everyone.
        # https://github.com/Kinto/kinto-signer/issues/55
        bucket_name = self.destination['bucket']
        collection_name = self.destination['collection']

        # Destination bucket will be writable by current user.
        perms = {'write': [request.prefixed_userid]}
        ensure_resource_exists(request=request,
                               resource_name='bucket',
                               parent_id='',
                               obj={FIELD_ID: bucket_name},
                               permissions=perms,
                               matchdict={'id': bucket_name})

        # Destination collection will be publicly readable.
        readonly_perms = {'read': (Everyone,)}
        ensure_resource_exists(request=request,
                               resource_name='collection',
                               parent_id=self.destination_bucket_uri,
                               obj={FIELD_ID: collection_name},
                               permissions=readonly_perms,
                               matchdict={
                                'bucket_id': bucket_name,
                                'id': collection_name
                               })

    def _get_records(self, resource, last_modified=None, empty_none=True):
        # If last_modified was specified, only retrieve items since then.
        storage_kwargs = {}
        if last_modified is not None:
            gt_last_modified = Filter(FIELD_LAST_MODIFIED, last_modified,
                                      COMPARISON.GT)
            storage_kwargs['filters'] = [gt_last_modified, ]

        storage_kwargs['sorting'] = [Sort(FIELD_LAST_MODIFIED, 1)]
        parent_id = "/buckets/{bucket}/collections/{collection}".format(**resource)

        records = self.storage.list_all(parent_id=parent_id,
                                        resource_name='record',
                                        include_deleted=True,
                                        **storage_kwargs)

        if len(records) == 0 and empty_none:
            # When the collection empty (no records and no tombstones)
            collection_timestamp = None
        else:
            collection_timestamp = self.storage.resource_timestamp(parent_id=parent_id,
                                                                   resource_name='record')

        return records, collection_timestamp

    def get_source_records(self, last_modified, **kwargs):
        return self._get_records(self.source, last_modified, **kwargs)

    def get_destination_records(self, **kwargs):
        return self._get_records(self.destination, **kwargs)

    def push_records_to_destination(self, request):
        __, dest_timestamp = self.get_destination_records()
        new_records, source_timestamp = self.get_source_records(last_modified=dest_timestamp)

        if source_timestamp and dest_timestamp and dest_timestamp > source_timestamp:
            raise ValueError("Destination collection timestamp cannot be higher "
                             "than source collection timestamp. Check that your "
                             "storage backend timezone is UTC.")

        # Update the destination collection.
        for record in new_records:
            storage_kwargs = {
                "parent_id": self.destination_collection_uri,
                "resource_name": 'record',
            }
            try:
                before = self.storage.get(object_id=record[FIELD_ID],
                                          **storage_kwargs)
            except RecordNotFoundError:
                before = None

            deleted = record.get('deleted', False)
            if deleted:
                try:
                    pushed = self.storage.delete(
                        object_id=record[FIELD_ID],
                        last_modified=record[FIELD_LAST_MODIFIED],
                        **storage_kwargs
                    )
                    action = ACTIONS.DELETE
                except RecordNotFoundError:
                    # If the record doesn't exists in the destination
                    # we are good and can ignore it.
                    continue
            else:
                if before is None:
                    pushed = self.storage.create(
                        obj=record,
                        **storage_kwargs)
                    action = ACTIONS.CREATE
                else:
                    pushed = self.storage.update(
                        object_id=record[FIELD_ID],
                        obj=record,
                        **storage_kwargs)
                    action = ACTIONS.UPDATE

            matchdict = {
                'bucket_id': self.destination['bucket'],
                'collection_id': self.destination['collection'],
                FIELD_ID: record[FIELD_ID]
            }
            record_uri = ('/buckets/{bucket_id}'
                          '/collections/{collection_id}'
                          '/records/{id}'.format(**matchdict))
            notify_resource_event(
                request,
                {'method': 'DELETE' if deleted else 'PUT',
                 'path': record_uri},
                matchdict=matchdict,
                resource_name="record",
                parent_id=self.destination_collection_uri,
                obj=pushed,
                action=action,
                old=before)

    def set_destination_signature(self, signature, source_attributes, request):
        # Push the new signature to the destination collection.
        parent_id = '/buckets/%s' % self.destination['bucket']
        collection_id = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            resource_name=collection_id,
            object_id=self.destination['collection'])

        # Update the collection_record
        new_collection = dict(**collection_record)
        new_collection.pop(FIELD_LAST_MODIFIED, None)
        new_collection['signature'] = signature
        # Copy some Kinto-Admin UI attributes from source to destination.
        for attr in ('sort', 'displayFields', 'attachment'):
            if attr in source_attributes:
                new_collection.setdefault(attr, source_attributes[attr])

        updated = self.storage.update(
            parent_id=parent_id,
            resource_name=collection_id,
            object_id=self.destination['collection'],
            obj=new_collection)

        matchdict = dict(bucket_id=self.destination['bucket'],
                         id=self.destination['collection'])
        notify_resource_event(
            request,
            {
                'method': 'PUT',
                'path': self.destination_collection_uri
            },
            matchdict=matchdict,
            resource_name="collection",
            parent_id=self.destination_bucket_uri,
            obj=updated,
            action=ACTIONS.UPDATE,
            old=collection_record)

    def update_source_review_request_by(self, request):
        current_date = datetime.datetime.now(datetime.timezone.utc).isoformat()
        attrs = {TRACKING_FIELDS.LAST_REVIEW_REQUEST_BY.value: request.prefixed_userid,
                 TRACKING_FIELDS.LAST_REVIEW_REQUEST_DATE.value: current_date}
        return self._update_source_attributes(request, **attrs)

    def update_source_status(self, status, request, old_status=None):
        current_userid = request.prefixed_userid
        current_date = datetime.datetime.now(datetime.timezone.utc).isoformat()
        attrs = {'status': status.value}
        if status == STATUS.WORK_IN_PROGRESS:
            attrs[TRACKING_FIELDS.LAST_EDIT_BY.value] = current_userid
            attrs[TRACKING_FIELDS.LAST_EDIT_DATE.value] = current_date
        if status == STATUS.TO_REVIEW:
            attrs[TRACKING_FIELDS.LAST_REVIEW_REQUEST_BY.value] = current_userid
            attrs[TRACKING_FIELDS.LAST_REVIEW_REQUEST_DATE.value] = current_date
        if status == STATUS.SIGNED:
            if old_status != STATUS.SIGNED:
                # Do not keep track of reviewer when refreshing signature.
                attrs[TRACKING_FIELDS.LAST_REVIEW_BY.value] = current_userid
                attrs[TRACKING_FIELDS.LAST_REVIEW_DATE.value] = current_date
            attrs[TRACKING_FIELDS.LAST_SIGNATURE_BY.value] = current_userid
            attrs[TRACKING_FIELDS.LAST_SIGNATURE_DATE.value] = current_date
        return self._update_source_attributes(request, **attrs)

    def _update_source_attributes(self, request, **kwargs):
        parent_id = '/buckets/%s' % self.source['bucket']
        resource_name = 'collection'

        collection_record = self.storage.get(
            parent_id=parent_id,
            resource_name=resource_name,
            object_id=self.source['collection'])

        # Update the collection_record
        new_collection = dict(**collection_record)
        new_collection.update(**kwargs)

        # Remove last_modified to be sure it's bumped.
        new_collection.pop('last_modified', None)

        updated = self.storage.update(
            parent_id=parent_id,
            resource_name=resource_name,
            object_id=self.source['collection'],
            obj=new_collection)

        matchdict = dict(bucket_id=self.source['bucket'],
                         id=self.source['collection'])
        notify_resource_event(
            request,
            {
                'method': 'PUT',
                'path': self.source_collection_uri
            },
            matchdict=matchdict,
            resource_name="collection",
            parent_id=self.source_bucket_uri,
            obj=updated,
            action=ACTIONS.UPDATE,
            old=collection_record)

    def invalidate_cloudfront_cache(self, request, timestamp):
        settings = request.registry.settings
        distribution_id = settings.get('signer.distribution_id')

        if not distribution_id:
            return

        paths = aslist(settings.get('signer.invalidation_paths', '/v1/*'))

        # Paths can have placeholders with destination bucket/collection
        bid = self.destination['bucket']
        cid = self.destination['collection']
        paths = [p.format(bucket_id=bid, collection_id=cid) for p in paths]

        try:
            # Create a boto client
            client = boto3.client('cloudfront')
            client.create_invalidation(
                DistributionId=distribution_id,
                InvalidationBatch={
                    'Paths': {
                        'Quantity': len(paths),
                        'Items': paths
                    },
                    'CallerReference': '{}-{}'.format(timestamp, uuid.uuid4())
                })
            logger.info("Invalidated CloudFront cache at %s" % ", ".join(paths))
        except Exception:
            logger.exception("Cache invalidation request failed.")
