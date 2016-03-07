from pyramid.settings import aslist


def parse_resources(raw_resources):
    resources = {}
    for res in aslist(raw_resources):
        if ";" not in res:
            msg = ("Resources should be defined as "
                   "'bucket/coll;bucket/coll'. Got %r" % res)
            raise ValueError(msg)
        source, destination = res.split(';')

        def _get_resource(resource):
            parts = resource.split('/')
            if len(parts) != 2:
                msg = ("Resources should be defined as bucket/collection. "
                       "Got %r" % resource)
                raise ValueError(msg)
            return {
                'bucket': parts[0],
                'collection': parts[1]
            }

        resources[source] = {
            'source': _get_resource(source),
            'destination': _get_resource(destination),
        }
    return resources
