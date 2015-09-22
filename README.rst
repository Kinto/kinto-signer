Kinto updater
#############

What does this do?
==================

This will:

1. Gather the latest changes from the server,
2. Check their validity

  2a. check the validity of the signature (with the pub key)
  2b. compute the collection hash locally;
  2c. compare it with the one stored in the collection;

3. Compute a new hash, sign it and upload everything to the server.

How to install?
===============

::

  $ mkvirtualenv kinto-updater
  $ pip install -r requirements.txt

How to use it?
==============

Once installed, in order to use it, you can use the `kinto-update` script, like
this::

  $ ./kinto-update --records=new-records.json --pubkey=pubkey.jwk --privkey=privkey.jwk

How to run the tests?
=====================

In order to run the tests, you need to install the dev environment, and then
invoke py.test::

  $ pip install -r dev-requirements.txt
  $ py.test

