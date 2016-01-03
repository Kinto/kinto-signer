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

How to keep S up to date
------------------------

1. Gather the latest changes from A,
2. Check their validity

  2a. check the validity of the signature (with the pub key)
  2b. compute the collection hash locally;
  2c. compare it with the one stored in the collection;

You can run a command to verify this, by doing::

    $ kinto_updater gather-changes --

How to install?
===============

::

  $ mkvirtualenv kinto-updater
  $ pip install -r requirements.txt


How to run the tests?
=====================

In order to run the tests, you need to install the dev environment, and then
invoke py.test::

  $ pip install -r dev-requirements.txt
  $ py.test

Architecture
============

We have two parts: one one side, there is a client that's able to replicate
a collection from one server to another one, using a local cache. It checks
that the signature is valid at the same time.

On the other hand, we have a hook that's triggered when new items are sent to
the Kinto server. It does the following:

1. Compute the hash + signature of all the records in the database.
2. Gather all the local changes, since the last timestamp that was synced.
3. Send them to the remote, using a BATCH with PUTs + PATCH for the coll.
