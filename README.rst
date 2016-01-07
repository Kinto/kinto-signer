Kinto updater
#############

|travis|

.. |travis| image:: https://travis-ci.org/mozilla-services/kinto-updater.svg?branch=master
    :target: https://travis-ci.org/mozilla-services/kinto-updater


What does this do?
==================

Consider two Kinto instances: "A, the authoritative" and "S, the signer".

How to sign data
----------------

0. When S starts-up, it retrieves all the records from A and stores the
   "last_modified" value of the collection.
1. A client sends updates to S. When all the data has been sent, a specific
   field is updated on the collection to ask the signer to sign the collection.
2. The signer gets all its local data (of the collection), computes a hash and
   generates a signature out of it.
3. The signature + the modified elements are sent to A.
4. Then, the signer updates its current collection status back to "signed" (with
   the signature and hash).

How to test the signature flow
==============================

In order to test the signature flow, you can run the functional tests::

  $ make run-remote
  $ make run-signer
  $ make functional
