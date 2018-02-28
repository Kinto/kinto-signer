import re
import pkg_resources
import functools

import transaction
from kinto.core.events import ACTIONS, ResourceChanged
from pyramid.exceptions import ConfigurationError
from pyramid.events import NewRequest
from pyramid.settings import asbool

from kinto_signer.signer import heartbeat
from kinto_signer import utils
from kinto_signer import listeners

#: Module version, as defined in PEP-0396.
__version__ = pkg_resources.get_distribution(__package__).version


DEFAULT_SIGNER = "kinto_signer.signer.local_ecdsa"


def includeme(config):
    # Register heartbeat to check signer integration.
    config.registry.heartbeats['signer'] = heartbeat

    settings = config.get_settings()

    # Check source and destination resources are configured.
    raw_resources = settings.get('signer.resources')
    if raw_resources is None:
        error_msg = "Please specify the kinto.signer.resources setting."
        raise ConfigurationError(error_msg)
    resources = utils.parse_resources(raw_resources)

    defaults = {
        "reviewers_group": "reviewers",
        "editors_group": "editors",
        "to_review_enabled": False,
        "group_check_enabled": False,
    }

    global_settings = {}

    config.registry.signers = {}
    for key, resource in resources.items():

        server_wide = 'signer.'
        bucket_wide = 'signer.{bucket}.'.format(**resource['source'])

        if resource['source']['collection'] is not None:
            collection_wide = 'signer.{bucket}_{collection}.'.format(**resource['source'])
            signers_prefixes = [(key, [collection_wide, bucket_wide, server_wide])]
        else:
            # If collection is None, it means the resource was configured for the whole bucket.
            signers_prefixes = [(key, [bucket_wide, server_wide])]
            # Iterate on settings to see if a specific signer config exists for
            # a collection within this bucket.
            bid = resource['source']['bucket']
            # Match setting names like signer.stage_specific.autograph.hawk_id
            matched = [re.search('signer\.{0}_([^\.]+)\.(.+)'.format(bid), k)
                       for k, v in settings.items()]
            for cid, unprefixed_setting_name in [m.groups() for m in matched if m]:
                if unprefixed_setting_name in listeners.REVIEW_SETTINGS:
                    # No need to have a custom signer for specific review settings.
                    continue
                # A specific signer will be instantiated and stored in the registry
                # with collection URI key since at least one of its parameter is specific.
                signer_key = "/buckets/{0}/collections/{1}".format(bid, cid)
                # Define the list of prefixes for this collection. This will allow
                # to mix collection specific with global defaults for signer settings.
                collection_wide = 'signer.{0}_{1}.'.format(bid, cid)
                signers_prefixes += [(signer_key, [collection_wide, bucket_wide, server_wide])]

        # Instantiates the signers associated to this resource.
        for signer_key, prefixes in signers_prefixes:
            dotted_location = utils.get_first_matching_setting('signer_backend',
                                                               settings,
                                                               prefixes,
                                                               default=DEFAULT_SIGNER)
            signer_module = config.maybe_dotted(dotted_location)
            backend = signer_module.load_from_settings(settings, prefixes=prefixes)
            config.registry.signers[signer_key] = backend

        # Load the setttings associated to each resource.
        for setting in listeners.REVIEW_SETTINGS:
            default = defaults[setting]
            # Global to all collections.
            global_settings[setting] = settings.get("signer.%s" % setting, default)
            # Per collection/bucket:
            value = utils.get_first_matching_setting(setting, settings, prefixes)
            if value is None:
                value = default
            config_value = value

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

            # Only store if relevant.
            if config_value != default:
                resource[setting] = value

    # Expose the capabilities in the root endpoint.
    message = "Digital signatures for integrity and authenticity of records."
    docs = "https://github.com/Kinto/kinto-signer#kinto-signer"
    config.add_api_capability("signer", message, docs,
                              version=__version__,
                              resources=resources.values(),
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

    sign_data_listener = functools.partial(listeners.sign_collection_data,
                                           resources=resources)

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
