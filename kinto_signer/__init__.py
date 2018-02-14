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


def _signer_dotted_location(settings, resource):
    """
    Returns the Python dotted location for the specified `resource`, along
    the associated settings prefix.

    If a ``signer_backend`` setting is defined for a particular bucket
    or a particular collection, then use the same prefix for every other
    settings names.

    .. note::

        This means that every signer settings must be duplicated for each
        dedicated signer.
    """
    prefix = 'signer.'
    bucket_wide = '{bucket}.'.format(**resource['source'])
    collection_wide = '{bucket}_{collection}.'.format(**resource['source'])

    prefixes = [prefix + collection_wide, prefix + bucket_wide, prefix]

    backend_setting_value = utils.get_first_matching_setting('signer_backend', settings, prefixes)

    # Fallback to the local ECDSA signer.
    default_signer_module = "kinto_signer.signer.local_ecdsa"
    signer_dotted_location = backend_setting_value or default_signer_module

    return signer_dotted_location, prefixes


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

    # Default global settings values.
    defaults = {
        "to_review_enabled": False,
        "group_check_enabled": False,
        "reviewers_principal": "/buckets/{bucket_id}/groups/reviewers",
        "editors_principal": "/buckets/{bucket_id}/groups/editors",
    }
    # Iterate over configured resources and resolves associated settings.
    config.registry.signers = {}
    for key, resource in resources.items():
        # Load the signers associated to each resource.
        dotted_location, prefixes = _signer_dotted_location(settings, resource)
        signer_module = config.maybe_dotted(dotted_location)
        backend = signer_module.load_from_settings(settings, prefixes=prefixes)
        config.registry.signers[key] = backend

        # Load the setttings associated to each resource.
        bucket_wide = "{source[bucket]}".format(**resource)
        collection_wide = "{source[bucket]}_{source[collection]}".format(**resource)
        for setting in ("reviewers_principal", "editors_principal",
                        "to_review_enabled", "group_check_enabled"):
            value = settings.get("signer.%s.%s" % (collection_wide, setting))
            if value is None:
                # By bucket.
                value = settings.get("signer.%s.%s" % (bucket_wide, setting))
                if value is None:
                    # Globally.
                    value = settings.get("signer.%s" % setting, defaults[setting])
            # Resolve placeholder with source info.
            if setting.endswith("_principal"):
                value = value.format(bucket_id=resource['source']['bucket'],
                                     collection_id=resource['source']['collection'])
            if setting.endswith("_enabled"):
                value = asbool(value)
            resource[setting] = value

    # Expose the capabilities in the root endpoint.
    message = "Digital signatures for integrity and authenticity of records."
    docs = "https://github.com/Kinto/kinto-signer#kinto-signer"
    config.add_api_capability("signer", message, docs,
                              version=__version__,
                              resources=resources.values())

    config.add_subscriber(
        functools.partial(listeners.set_work_in_progress_status,
                          resources=resources),
        ResourceChanged,
        for_resources=('record',))

    config.add_subscriber(
        functools.partial(listeners.check_collection_status,
                          resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
        for_resources=('collection',))

    config.add_subscriber(
        functools.partial(listeners.check_collection_tracking,
                          resources=resources),
        ResourceChanged,
        for_actions=(ACTIONS.CREATE, ACTIONS.UPDATE),
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
