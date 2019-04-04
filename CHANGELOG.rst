Changelog
=========

This document describes changes between each past release.

5.0.0 (2019-04-04)
------------------

**Breaking changes**

- Do not invalidate CloudFront on signature refresh (fixes #430)


4.0.1 (2019-01-30)
------------------

**Security issue**

- Signer parameters were displayed in capabilities. Fixed in #326.


4.0.0 (2019-01-22)
------------------

**Bug fixes**

- Fix inconsistencies when source records are deleted via the DELETE /records endpoint (fixes #287)

**Breaking changes**

- Require Kinto >= 12.0.0


3.3.9 (2018-12-10)
------------------

**Internal Changes**

- Do not use the count value from ``storage.get_all()``


3.3.8 (2018-11-27)
------------------

- Fix "RuntimeError: OrderedDict mutated during iteration" (#283).


3.3.7 (2018-11-20)
------------------

**Bug fixes**

- If ``to_review_enabled`` is False, the preview collection is not created, nor updated (fixes #279)
- Show collections with specific settings in capabilities


3.3.6 (2018-11-08)
------------------

**Bug fixes**

- Fix Canonical JSON serialization of zero
- Allow installing ``kinto-signer`` with ``--no-deps`` in order to import ``kinto_signer.serializer.canonical_json()`` without the Pyramid ecosystem


3.3.5 (2018-11-06)
------------------

**Bug fixes**

- Fix Canonical JSON about float numbers to conform with `ECMAScript V6 notation <https://www.ecma-international.org/ecma-262/6.0/#sec-tostring-applied-to-the-number-type>`_


3.3.4 (2018-10-25)
------------------

**Bug fixes**

- Prevent events to be sent if status is not changed (#268)

**Internal Changes**

- Rewrite e2e to use ``.get_records_timestamp()`` (#258)
- Enable Wheel distribution (fixes #271)


3.3.3 (2018-10-10)
------------------

- Allow refresh of signature even if the collection was never signed (#267)


3.3.2 (2018-08-20)
------------------

- Support kinto 10.0.0, which allowed some simplifications (#264).


3.3.1 (2018-08-17)
------------------

- Failed artifact produced by mistake. Please ignore.


3.3.0 (2018-07-24)
------------------

**New features**

- Allow to refresh the signature when the collection has pending changes (fixes #245)


3.2.5 (2018-07-05)
------------------

**Bug fixes**

- Fix ``scripts/e2e.py`` script to work with per-bucket configuration
- Prevent kinto-attachment to raise errors when attachments are updated (fixes #256)i

3.2.4 (2018-05-30)
------------------

**Bug fixes**

- Fix CloudFront invalidation request with multiple paths (fixes #253)


3.2.3 (2018-05-07)
------------------

**Bug fixes**

- Fix crash on collection delete (fixes #248)


3.2.2 (2018-05-02)
------------------

**Bug fixes**

- Cleanup preview and destination when source collection is deleted (fixes #114)


3.2.1 (2018-04-25)
------------------

**Bug fixes**

- Make sure the dates in tracking fields are given on the UTC timezone


3.2.0 (2018-04-11)
------------------

**Deprecations**

- The collection specific settings must now be separated with ``.`` instead of ``_``.
  (eg. use ``kinto.signer.staging.certificates.editors_group`` instead of ``kinto.signer.staging_certificates.editors_group``) (fixes #224)

**New features**

- Give write permission to reviewers/editors groups on newly created collections (fixes #237)
- The preview collection signature is now refreshed along the destination (fixes #236)
- Tracking fields are now documented and new ones were added (``last_edit_date``, ``last_request_review_date``, ``last_review_date`` and ``last_signature_date``) (fixes #137)

**Internal changes**

- Now log an INFO message when the CloudFront invalidation request is sent (fixes #238)


3.1.0 (2018-03-16)
------------------

**New features**

- Cloudfront invalidation paths can be configured
- User does not have to be in the *reviewers* group to refresh a signature (fixes #233)

**Internal changes**

- Got rid of ``six`` since *kinto-signer* is Python 3 only.


3.0.0 (2018-03-08)
------------------

**Breaking changes**

- The settings ``reviewers_group``, ``editors_group``, ``to_review_enabled``, ``group_check_enabled``
  prefixed with ``_`` are not supported anymore. (eg. use ``kinto.signer.staging_certificates.editors_group``
  instead of ``kinto.signer.staging_certificates_editors_group``)

**New features**

- Allow spaces in resources configurations, and separate URIs with ``->`` for better readability (fixes #148, fixes #88)
- Allow configuration of ``reviewers_group``, ``editors_group``, ``to_review_enabled``, ``group_check_enabled``
  by bucket
- Allow placeholders ``{bucket_id}`` and ``{collection_id}`` in ``reviewers_group``, ``editors_group``,
  ``to_review_enabled``, and ``group_check_enabled`` settings
  (e.g. ``group:/buckets/{bucket_id}/groups/{collection_id}-reviewers``) (fixes #210)
- Allow configuration by bucket. Every collections in the source bucket will be reviewed/signed (fixes #144).
- Editors and reviewers groups are created automatically when source collection is created (fixes #213)
- Preview and destination collections are automatically signed when source is created (fixes #226)

**Bug fixes**

- Fix permissions of automatically created preview/destination bucket (fixes #155)


2.2.0 (2017-12-06)
------------------

- Use generic config keys as a fallback for missing specific signer config keys. (#151)
- Fix bad signature on empty collections. (#164)


2.1.1 (2017-10-27)
------------------

- Invalidate the CloudFront CDN cache. (#199)


2.1.0 (2017-08-07)
------------------

**New features**

- Invalidate the monitor changes collection on updates (#187)

**Bug fixes**

- Allow kinto-attachment collections reviews. (#190)
- Remove additional / in invalidation collection path (#194)


2.0.0 (2017-07-05)
------------------

**Breaking changes**

- Upgrade to autograph 2.0


1.5.2 (2017-06-28)
------------------

**Bug fixes**

- Catch cache invalidation errors and log the error. (#186)


1.5.1 (2017-06-28)
------------------

**Bug fixes**

- Do not make the heartbeat fail on missing x5u. (#182)


1.5.0 (2017-06-19)
------------------

**New features**

- Add support for CloudFront path cache invalidation. (#178)

.. code-block:: ini

    # Configure the cloudfront distribution related to the server cache.
    kinto.signer.distribution_id = E2XLCI5EUWMRON


1.4.0 (2017-06-07)
------------------

**Internal changes**

- Upgrade to kinto-http 9.0
- Upgrade to kinto 7.1


1.3.3 (2017-04-18)
------------------

**Bug fixes**

- Do not send ``ReviewApproved`` event when signing a collection that is already signed (fixes #174)


1.3.2 (2017-03-21)
------------------

**Bug fixes**

- Send kinto-signer before committing since some database may have to be performed
  in the subscribers (#172)


1.3.1 (2017-03-17)
------------------

**Bug fixes**

- Allow ``canonical_json`` to work with iterators. (#167)
- Fixed inconsistencies in ``ResourceChanged`` produced by Kinto signer (#169)


1.3.0 (2017-03-03)
------------------

**Bug fixes**

- Update e2e.py to be robust against kinto_client returning an iterator in Python 3. (#165)


1.2.0 (2017-01-20)
------------------

**Bug fixes**

- Do not always reset destination permissions

**New features**

- Pyramid events are sent for each review step of the validation workflow (fixes #157)
- Kinto Admin UI fields like ``displayFields`` ``attachment`` and ``sort`` are copied
  from the source to the preview and destination collections (if not set) (fixes #161)


1.1.1 (2017-01-17)
------------------

**Bug fixes**

- Fix consistency of setting names for per-collection workflows configuration (fixes #149)
- Remove recursivity of events when requesting review (#158)


1.0.0 (2016-10-26)
------------------

**New features**

- Add ability to configure group names and enable review/group check by collection
  (fixes #145)


0.9.2 (2016-10-06)
------------------

**Bug fixes**

- Fix decoration of listener when StatsD is enabled (fixes #138)
  Related to https://github.com/jsocol/pystatsd/issues/85
- Use a dedicated ``errno`` in 403 responses when operation is forbidden (fixes #135)
- Make sure that collection editor can retrigger a signature (fixes #136)


0.9.1 (2016-10-03)
------------------

**Bug fixes**

- Do not check that editor is different than reviewer if *review* is not enabled (fixes #131)


0.9.0 (2016-09-30)
------------------

**New features**

- Now sends a StatsD timer with signature duration at ``plugins.signer``
- Ability to define a *preview* collection that is updated when collection status
  is set to ``to-review``. In order to enable this feature, define triplets in
  the ``kinto_signer.ressources`` settings (``{source};{preview};{destination}``)
  instead of couples, and make sure you have ``kinto.signer.to_review_enabled = true``.
  See README for more info (fixes #126)


0.8.1 (2016-08-26)
------------------

**Bug fixes**

- Warn if the storage backend timezone is not configured to use UTC (#122)
- Fix signing when all records have been deleted from the source (#120)


0.8.0 (2016-08-23)
------------------

Now requires *kinto >= 3.3*.

**New features**

- The API can now rely on a workflow and can check that users changing collection status
  belong to some groups (e.g. ``editors``, ``reviewers``).
- When a change is made in the source collection, its status is switched to
  ``work-in-progress``
- When a collection is modified, the ``last-author`` attribute is set to the current userid.
  When set to ``to-review``, the ``last_editor`` value is set, and when set to ``to-sign``
  the ``last_reviewer`` value is set.

**Bug fixes**

- Fix crash when several collections are created with status: to-sign using
  a batch request (fixes #116)


0.7.3 (2016-07-27)
------------------

**Bug fixes**

- Fix signature inconsistency (timestamp) when several changes are sent from
  the *source* to the *destination* collection.
  Fixed ``e2e.py`` and ``validate_signature.py`` scripts (fixes #110)

**Minor change**

- Add the plugin version in the capability. (#108)

0.7.2 (2016-07-25)
------------------

**Bug fixes**

- Provide the ``old`` value on destination records updates (#104)
- Send ``create`` event when destination record does not exist yet.
- Events sent by kinto-signer for created/updated/deleted objects in destination now show
  user_id as ``plugin:kinto-signer``

0.7.1 (2016-07-21)
------------------

*kinto-signer* now requires bug fixes that were released in Kinto 3.2.4 and Kinto 3.3.2.

**Bug fix**

- Update the `last_modified` value when updating the collection status and signature (#97)
- Prevents crash with events on ``default`` bucket on Kinto < 3.3
- Trigger ``ResourceChanged`` events when the destination collection and records are updated
  during signing. This allows plugins like ``kinto-changes`` and ``kinto.plugins.history``
  to catch the changes (#101).


0.7.0 (2016-06-28)
------------------

**Breaking changes**

- The collection timestamp is now included in the payload prior to signing.
  Old clients won't be able to verify the signature made by this version.

**New features**

- Raise configuration errors if resources are not configured correctly (ref #88)


0.6.0 (2016-05-19)
------------------

- Update to ``kinto.core`` for compatibility with Kinto 3.0. This
  release is no longer compatible with Kinto < 3.0, please upgrade!


0.5.0 (2016-05-17)
------------------

**Bug fix**

- Do not crash on record deletion if destination was never synced (#82)

**Internal changes**

- Rename ``get_local_records`` to ``get_source_records`` (#83)
- Rename ``sign_and_update_remote`` to ``sign_and_update_destination`` (#85)


0.4.0 (2016-05-10)
------------------

**New features**

- Ability to define a different signer per collection (#52)

**Bug fix**

- Return 503 instead of 500 when signing fails (fixes #71)

**Internal changes**

- Removed scary diagram with Mozilla specific stuff (#60)


0.3.0 (2016-04-26)
------------------

**Breaking changes**

- Change the format of exposed settings in the root URL capabilities (fixes #63)
- The ``hook.py`` module was deleted, meaning that if ``kinto_signer.hook`` was
  used in ``kinto.includes`` setting, it will break.
  Use ``kinto.includes = kinto_signer`` instead.
- Switch to ``Content-Signature`` spec, as by provided Autograph and expected
  by Firefox Personal Security Manager.
  Mainly means that ``Content-Signature:\x00`` has to be prepended to payload
  prior to signing verification.

**New features**

- Add signer entry in heartbeat view (fixes #50)
- Change the source/destination settings format (fixes #35). Old format is still
  supported.

**Internal changes**

- Fix test coverage for resource event (#59)
- Add more tests for canonical JSON serializers (#58)
- Add a end-to-end smoke script to be ran on a Kinto instance (#64)

0.2.0 (2016-03-22)
------------------

- Update autograph to version 1.1.0


0.1.0 (2016-03-07)
-------------------

- Provide a hook that triggers a signature on the current local collection and
  replicate it to the destination collection.
- Provide a local ECDSA signer.
- Provide a remote Autograph signer.
- Handle addition and deletion of records during the replication.
- Support multiple source and destination resources
