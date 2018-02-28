from collections import OrderedDict

from kinto.views import NameGenerator

from enum import Enum
from pyramid.settings import aslist
from pyramid.exceptions import ConfigurationError


class STATUS(Enum):
    WORK_IN_PROGRESS = 'work-in-progress'
    TO_SIGN = 'to-sign'
    TO_REVIEW = 'to-review'
    SIGNED = 'signed'

    def __eq__(self, other):
        if not hasattr(other, 'value'):
            return self.value == other
        return super(STATUS, self).__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)


def parse_resources(raw_resources):
    resources = OrderedDict()

    name_generator = NameGenerator()

    for res in aslist(raw_resources):
        error_msg = "Malformed resource: %%s (in %r). See kinto-signer README." % res
        if ";" not in res:
            raise ConfigurationError(error_msg % "not separated with ';'")

        try:
            triplet = res.strip(';').split(';')
            if len(triplet) == 2:
                source, destination = triplet
                preview = None
            else:
                source, preview, destination = triplet
        except ValueError:
            raise ConfigurationError(error_msg % "should be a pair or a triplet")

        def _get_resource(resource):
            parts = resource.split('/')
            if len(parts) == 2:
                bucket, collection = parts
            elif len(parts) == 3 and parts[1] == 'buckets':
                # /buckets/bid
                _, _, bucket = parts
                collection = None
            elif len(parts) == 5 and parts[1] == 'buckets' and parts[3] == 'collections':
                # /buckets/bid/collections/cid
                _, _, bucket, _, collection = parts
            else:
                raise ConfigurationError(error_msg % "should be a bucket or collection URI")
            valid_ids = (name_generator.match(bucket) and
                         (collection is None or name_generator.match(collection)))
            if not valid_ids:
                raise ConfigurationError(error_msg % "bucket or collection id is invalid")
            return {
                'bucket': bucket,
                'collection': collection
            }

        source = _get_resource(source)
        destination = _get_resource(destination)

        if source['collection'] is None:
            # Per bucket.
            key = '/buckets/{bucket}'.format(**source)
        else:
            # For a specific collection.
            key = '/buckets/{bucket}/collections/{collection}'.format(**source)

        resources[key] = {
            'source': source,
            'destination': destination,
        }
        if preview is not None:
            resources[key]['preview'] = _get_resource(preview)
        # XXX: raise if mix-up of per-bucket/specific collection
        # XXX: raise if same bid/cid twice/thrice

    return resources


def get_first_matching_setting(setting_name, settings, prefixes):
    for prefix in prefixes:
        prefixed_setting_name = '{}{}'.format(prefix, setting_name)
        if prefixed_setting_name in settings:
            return settings[prefixed_setting_name]
