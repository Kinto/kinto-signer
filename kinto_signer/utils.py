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
