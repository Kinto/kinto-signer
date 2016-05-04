from collections import OrderedDict
from pyramid.settings import aslist


def parse_resources(raw_resources):
    resources = OrderedDict()
    for res in aslist(raw_resources):
        error_msg = ("Resources should be defined as "
                     "'/buckets/<bid>/collections/<cid>;"
                     "/buckets/<bid>/collections/<cid>'. Got %r" % res)
        if ";" not in res:
            raise ValueError(error_msg)
        source, destination = res.split(';')

        def _get_resource(resource):
            parts = resource.split('/')
            if len(parts) == 2:
                bucket, collection = parts
            elif len(parts) == 5:
                _, _, bucket, _, collection = parts
            else:
                raise ValueError(error_msg)
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
