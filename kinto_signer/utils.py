from pyramid.settings import aslist


def get_setting(settings, key, bucket=None, collection=None, default=None):
    """Load resource setting.

    Looks first for resource specific keys and then service-wide keys
    in the settings and returns the first it encounters.
    """
    res_specific_key = 'signer.{0}_{1}.{2}'.format(bucket, collection, key)
    service_wide_key = 'signer.{key}'.format(key=key)
    value = settings.get(res_specific_key,
                         settings.get(service_wide_key, default))
    return value


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
