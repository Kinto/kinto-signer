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
        error_msg = ("Resources should be defined as "
                     "'/buckets/<bid>/collections/<cid>;"
                     "/buckets/<bid>/collections/<cid>' and "
                     "separated with space or linebreaks. Got %r" % res)
        if ";" not in res:
            raise ConfigurationError(error_msg)

        try:
            triplet = res.strip(';').split(';')
            if len(triplet) == 2:
                source, destination = triplet
                preview = None
            else:
                source, preview, destination = triplet
        except ValueError:
            raise ConfigurationError(error_msg)

        def _get_resource(resource):
            parts = resource.split('/')
            if len(parts) == 2:
                bucket, collection = parts
            elif len(parts) == 5:
                _, _, bucket, _, collection = parts
            else:
                raise ConfigurationError(error_msg)
            valid_ids = (name_generator.match(bucket) and
                         name_generator.match(collection))
            if not valid_ids:
                raise ConfigurationError(error_msg)
            return {
                'bucket': bucket,
                'collection': collection
            }

        pattern = '/buckets/{bucket}/collections/{collection}'
        source = _get_resource(source)
        destination = _get_resource(destination)
        key = pattern.format(**source)
        resources[key] = {
            'source': source,
            'destination': destination,
        }
        if preview is not None:
            resources[key]['preview'] = _get_resource(preview)

    return resources
