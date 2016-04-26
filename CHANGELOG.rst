Changelog
=========

This document describes changes between each past release.

0.3.0 (unreleased)
------------------

- Add signer entry in heartbeat view (fixes #50)
- Switch to ``Content-Signature`` spec, as by provided Autograph and expected
  by Firefox Personal Security Manager

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
