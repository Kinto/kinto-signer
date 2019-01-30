import copy
import re
import pkg_resources
import functools

#: Module version, as defined in PEP-0396.
__version__ = pkg_resources.get_distribution(__package__).version


DEFAULT_SIGNER = "kinto_signer.signer.local_ecdsa"


def get_exposed_resources(resource_dict, review_settings):
    """Compute a set of resources to be shown as part of the server's capabilities.

    This should include review settings for each resource but nothing
    related to the actual signing parameters for those resources."""
    out = []
    for resource in resource_dict.values():
        sanitized = {}
        for setting in ["source", "destination", "preview"] + list(review_settings):
            if setting in resource:
                sanitized[setting] = resource[setting]
        out.append(sanitized)

    return out


def includeme(config):
    # We import stuff here, so that kinto-signer can be installed with `--no-deps`
    # and used without having this Pyramid ecosystem installed.
    import transaction
    from kinto.core.events import ACTIONS, ResourceChanged
    from pyramid.exceptions import ConfigurationError
    from pyramid.events import NewRequest
    from pyramid.settings import asbool

    from kinto_signer.signer import heartbeat
    from kinto_signer import utils
    from kinto_signer import listeners

    # Register heartbeat to check signer integration.
    config.registry.heartbeats['signer'] = heartbeat

    settings = config.get_settings()

    # Check source and destination resources are configured.
    raw_resources = settings.get('signer.resources')
    if raw_resources is None:
        error_msg = "Please specify the kinto.signer.resources setting."
        raise ConfigurationError(error_msg)
    resources = utils.parse_resources(raw_resources)

    # Expand the resources with the ones that come from per-bucket resources
    # and have specific settings.
    # For example, consider the case where resource is ``/buckets/dev -> /buckets/prod``
    # and there is a setting ``signer.dev.recipes.signer_backend = foo``
    output_resources = resources.copy()
    for key, resource in resources.items():
        # If collection is not None, there is nothing to expand :)
        if resource['source']['collection'] is not None:
            continue
        bid = resource['source']['bucket']
        # Match setting names like signer.stage.specific.autograph.hawk_id
        matches = [(v, re.search(r'signer\.{0}\.([^\.]+)\.(.+)'.format(bid), k))
                   for k, v in settings.items()]
        found = [(v, m.group(1), m.group(2)) for (v, m) in matches if m]
        # Expand the list of resources with the ones that contain collection
        # specific settings.
        for setting_value, cid, setting_name in found:
            signer_key = "/buckets/{0}/collections/{1}".format(bid, cid)
            if signer_key not in output_resources:
                specific = copy.deepcopy(resource)
                specific["source"]["collection"] = cid
                specific["destination"]["collection"] = cid
                if "preview" in specific:
                    specific["preview"]["collection"] = cid
                output_resources[signer_key] = specific
            output_resources[signer_key][setting_name] = setting_value
    resources = output_resources

    # Determine which are the settings that apply to all buckets/collections.
    defaults = {
        "reviewers_group": "reviewers",
        "editors_group": "editors",
        "to_review_enabled": False,
        "group_check_enabled": False,
    }
    global_settings = {}
    for setting in listeners.REVIEW_SETTINGS:
        value = settings.get("signer.%s" % setting, defaults[setting])
        if setting.endswith("_enabled"):
            value = asbool(value)
        global_settings[setting] = value

    # For each resource that is configured, we determine what signer is
    # configured and what are the review settings.
    # Note: the `resource` values are mutated in place.
    config.registry.signers = {}
    for signer_key, resource in resources.items():

        server_wide = 'signer.'
        bucket_wide = 'signer.{bucket}.'.format(**resource['source'])
        prefixes = [bucket_wide, server_wide]

        per_bucket_config = resource['source']['collection'] is None

        if not per_bucket_config:
            collection_wide = 'signer.{bucket}.{collection}.'.format(**resource['source'])
            deprecated = 'signer.{bucket}_{collection}.'.format(**resource['source'])
            prefixes = [collection_wide, deprecated] + prefixes

        # Instantiates the signers associated to this resource.
        dotted_location = utils.get_first_matching_setting('signer_backend',
                                                           settings,
                                                           prefixes,
                                                           default=DEFAULT_SIGNER)
        signer_module = config.maybe_dotted(dotted_location)
        backend = signer_module.load_from_settings(settings, prefixes=prefixes)
        config.registry.signers[signer_key] = backend

        # Load the setttings associated to each resource.
        for setting in listeners.REVIEW_SETTINGS:
            # Per collection/bucket:
            value = utils.get_first_matching_setting(setting, settings, prefixes,
                                                     default=global_settings[setting])

            if setting.endswith("_enabled"):
                value = asbool(value)

            # Resolve placeholder with source info.
            if setting.endswith("_group"):
                # If configured per bucket, then we leave the placeholder.
                # It will be resolved in listeners during group checking and
                # by Kinto-Admin when matching user groups with info from capabilities.
                collection_id = resource['source']['collection'] or "{collection_id}"
                try:
                    value = value.format(bucket_id=resource['source']['bucket'],
                                         collection_id=collection_id)
                except KeyError as e:
                    raise ConfigurationError("Unknown group placeholder %s" % e)

            # Only expose if relevant.
            if value != global_settings[setting]:
                resource[setting] = value
            else:
                resource.pop(setting, None)

    # Expose the capabilities in the root endpoint.
    exposed_resources = get_exposed_resources(resources, listeners.REVIEW_SETTINGS)
    message = "Digital signatures for integrity and authenticity of records."
    docs = "https://github.com/Kinto/kinto-signer#kinto-signer"
    config.add_api_capability("signer", message, docs,
                              version=__version__,
                              resources=exposed_resources,
                              **global_settings)

    config.add_subscriber(
        functools.partial(listeners.set_work_in_progress_status,
                          resources=resources),
        ResourceChanged,
        for_resources=('record',))

    config.add_subscriber(
        functools.partial(listeners.check_collection_status,
                          resources=resources,
                          **global_settings),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',))

    config.add_subscriber(
        functools.partial(listeners.check_collection_tracking,
                          resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',))

    config.add_subscriber(
        functools.partial(listeners.create_editors_reviewers_groups,
                          resources=resources,
                          editors_group=global_settings["editors_group"],
                          reviewers_group=global_settings["reviewers_group"]),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE,),
        for_resources=('collection',))

    config.add_subscriber(
        functools.partial(listeners.cleanup_preview_destination,
                          resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.DELETE,),
        for_resources=('collection',))

    sign_data_listener = functools.partial(listeners.sign_collection_data,
                                           resources=resources,
                                           **global_settings)

    # If StatsD is enabled, monitor execution time of listener.
    if config.registry.statsd:
        # Due to https://github.com/jsocol/pystatsd/issues/85
        for attr in ('__module__', '__name__'):
            origin = getattr(listeners.sign_collection_data, attr)
            setattr(sign_data_listener, attr, origin)

        statsd_client = config.registry.statsd
        key = 'plugins.signer'
        sign_data_listener = statsd_client.timer(key)(sign_data_listener)

    config.add_subscriber(
        sign_data_listener,
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',))

    def on_new_request(event):
        """Send the kinto-signer events in the before commit hook.
        This allows database operations done in subscribers to be automatically
        committed or rolledback.
        """
        # Since there is one transaction per batch, ignore subrequests.
        if hasattr(event.request, 'parent'):
            return
        current = transaction.get()
        current.addBeforeCommitHook(listeners.send_signer_events,
                                    args=(event,))

    config.add_subscriber(on_new_request, NewRequest)
