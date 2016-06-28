from collections import OrderedDict

from kinto.views import NameGenerator

from pyramid.settings import aslist
from pyramid.exceptions import ConfigurationError


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
            source, destination = res.split(';')
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
    return resources
