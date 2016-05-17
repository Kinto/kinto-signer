Changelog
=========

This document describes changes between each past release.

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
