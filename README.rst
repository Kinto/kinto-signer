Kinto signer
#############

|travis|

.. |travis| image:: https://travis-ci.org/mozilla-services/kinto-signer.svg?branch=master
    :target: https://travis-ci.org/mozilla-services/kinto-signer


What does this do?
==================

**Kinto signer** is a `Kinto <https://kinto.readthedocs.org>`_ plugin that
makes it possible to sign the updates of Kinto collections. In other words,
it's a way to verify that the data the client has got is the data the original
authors intended to distribute.

This works with two Kinto instances:

- **A, the authority** (also known as "the signer"). It is where the original
  data are sent. The authority is configured to sign the data for a specific
  "origin".
- **O, the origin**, which will end up distributing the data and the signatures.
  It is where the client retrieve the data.

.. image::
   schema.png


Triggering a signature on the authority
=======================================

Once started, the authority is behaving like a normal Kinto server, until you
ask for a signature of the collection. To trigger this signature operation,
you need to add a specific field on the **collection**: ``status: "to-sign"``.

Here is how to do it with ```httpie``:

.. code-block::

  echo '{"data": {"status": "to-sign"}}' | http PATCH http://0.0.0.0:8888/v1/buckets/default/collections/tasks --auth user:pass

From there, the authority will:

1. Retrieve all records on the collection, compute a hash of the records, and
   generate a signature out of it.
2. Send all local changes to the Origin server, **with a signature**.
3. Update the collection metadata with ``status:signed``.

Configuring kinto-signer
========================

To install this plugin in a Kinto server, a few configuration variables need
to be set.

+---------------------------------+--------------------------------------------------------------------------+
| Setting name                    | What does it do?                                                         |
+=================================+==========================================================================+
| kinto_signer.remote_server_url  | The complete location of the remote server URL (the origin)              |
|                                 | For instance ``https://localhost:8000/v1/``                              |
+---------------------------------+--------------------------------------------------------------------------+
| kinto_signer.bucket             | The name of the bucket on which signatures will be applied.              |
|                                 | *Current limitation: the bucket should be the same locally and remotely* |
+---------------------------------+--------------------------------------------------------------------------+
| kinto_signer.collection         | The name of the collection on which signatures will be applied           |
|                                 | *Current limitation: the collection should be the same locally and       |
|                                 | remotely*                                                                |
+---------------------------------+--------------------------------------------------------------------------+
| kinto_signer.remote_server_auth | The authentication to use on the remote server. Should be specified as   |
|                                 | "user:password".                                                         |
+---------------------------------+--------------------------------------------------------------------------+
| kinto_signer.private_key        | The absolute path to the location of the ECDSA private key to use to     |
|                                 | apply the signatures                                                     |
+---------------------------------+--------------------------------------------------------------------------+

Here is an example of what a configuration could look like:

.. code-block:: ini

  kinto.includes = kinto_signer.hook

  kinto_signer.bucket = buck
  kinto_signer.collection = coll
  kinto_signer.remote_server_url = http://localhost:7777/v1
  kinto_signer.remote_server_auth = user:p4ssw0rd
  kinto_signer.private_key = kinto_signer/tests/config/ecdsa.private.pem

Starting the authority for the first time
=========================================

Each time the authority starts, it will reach the origin and get all the data
contained in configured bucket/collection of the origin.


Generating a keypair
====================

To generate a new keypair, you can use the following command::

  $ python -m kinto_signer.generate_keypair private.pem public.pem

Running the tests
=================
To run the unit tests::

  $ make tests

To the functional tests::

  $ make run-remote
  $ make run-signer
  $ make functional
