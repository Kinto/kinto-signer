Kinto signer
############

|travis|

.. |travis| image:: https://travis-ci.org/Kinto/kinto-signer.svg?branch=master
    :target: https://travis-ci.org/Kinto/kinto-signer

**Kinto signer** is a Kinto `Kinto <https://kinto.readthedocs.org>`_ plugin
that introduces [digital signatures](https://en.wikipedia.org/wiki/Digital_signature)
in order to guarantee integrity and authenticity of collections of records.


How does it work?
=================

**Kinto signer** uses two collections:

* The *source*, where the authors create/update/delete records.
* The *destination*, where the clients obtain the records and their signature.

When the *source* collection metadata ``status`` is set to ``to-sign``,
**Kinto-signer** will:

1. grab the whole list of records in this *source* collection
1. serialize it in a Canonical JSON form (*see below*)
1. compute a signature using the configured backend
1. update the *destination* collection records with the recent changes
1. update the *destination* collection metadata ``signature`` with the information
   obtain form the signature backend
1. set the *source* metadata ``status`` to ``signed``.

.. image::
   schema.png


Setup
=====

To install this plugin in a Kinto server, a few configuration variables need
to be set.

Here is an example of what a configuration could look like:

.. code-block:: ini

  kinto.includes = kinto_signer

  kinto.signer.resources =
      source/collection1;destination/collection1
      source/collection2;destination/collection2

+---------------------------------+--------------------------------------------------------------------------+
| Setting name                    | What does it do?                                                         |
+=================================+==========================================================================+
| kinto.signer.resources          | The name of the buckets and collections on which signatures can be       |
|                                 | triggered and the destination where the data and the signatures will     |
|                                 | end-up.                                                                  |
+---------------------------------+--------------------------------------------------------------------------+
| kinto.signer.signer_backend     | The python dotted location to the signer to use. By default, a local     |
|                                 | ECDSA signer will be used. Choices are either                            |
|                                 | ``kinto_signer.signer.local_ecdsa`` or ``kinto_signer.signer.autograph`` |
|                                 | Have a look at the sections below for more information.                  |
+---------------------------------+--------------------------------------------------------------------------+

Configuration for the (default) ECDSA local signer
--------------------------------------------------

+---------------------------------+--------------------------------------------------------------------------+
| Setting name                    | What does it do?                                                         |
+=================================+==========================================================================+
| kinto.signer.ecdsa.private_key  | Absolute path to the ECDSA private key to use to apply the signatures    |
+---------------------------------+--------------------------------------------------------------------------+
| kinto.signer.ecdsa.public_key   | Absolute path to the ECDSA private key to use to verify the signature    |
|                                 | (useful if you just want to use the signer as a verifier)                |
+---------------------------------+--------------------------------------------------------------------------+


Configuration for the Autograph signer
--------------------------------------

Kinto signer can integrate with the
`Autograph <https://github.com/mozilla-services/autograph>`_ server. To do so,
use the following settings:

+------------------------------------+--------------------------------------------------------------------------+
| Setting name                       | What does it do?                                                         |
+====================================+==========================================================================+
| kinto.signer.autograph.server_url  | The autograph server URL                                                 |
+------------------------------------+--------------------------------------------------------------------------+
| kinto.signer.autograph.hawk_id     | The hawk identifier used to issue the requests.                          |
+------------------------------------+--------------------------------------------------------------------------+
| kinto.signer.autograph.hawk_secret | The hawk secret used to issue the requests.                              |
+------------------------------------+--------------------------------------------------------------------------+


Usage
=====

Suppose we defined the following resources in the configuration:

.. code-block:: ini

    kinto.signer.resources = source/collection1;destination/collection1

First, if necessary, we create the appropriate Kinto objects, for example, with ``httpie``:

.. code-block:: bash

    $ http PUT http://0.0.0.0:8888/v1/buckets/source --auth user:pass
    $ http PUT http://0.0.0.0:8888/v1/buckets/source/collections/collection1 --auth user:pass
    $ http PUT http://0.0.0.0:8888/v1/buckets/destination --auth user:pass
    $ http PUT http://0.0.0.0:8888/v1/buckets/destination/collections/collection1 --auth user:pass

Create some records in the *source* collection.

.. code-block:: bash

    $ echo '{"data": {"article": "title 1"}}' | http POST http://0.0.0.0:8888/v1/buckets/source/collections/collection1/records --auth user:pass
    $ echo '{"data": {"article": "title 2"}}' | http POST http://0.0.0.0:8888/v1/buckets/source/collections/collection1/records --auth user:pass


Trigger a signature operation, set the ``status`` field on the *source* collection metadata to ``"to-sign"``.

.. code-block:: bash

    echo '{"data": {"status": "to-sign"}}' | http PATCH http://0.0.0.0:8888/v1/buckets/source/collections/collection1 --auth user:pass

The *destination* collection should now contain the new records:

.. code-block:: bash

    $ http GET http://0.0.0.0:8888/v1/buckets/destination/collections/collection1/records --auth user:pass

.. code-block:: javascript

    {
        "data": [
            {
                "article": "title 2",
                "id": "a45c74a4-18c9-4bc2-bf0c-29d96badb9e6",
                "last_modified": 1460558489816
            },
            {
                "article": "title 1",
                "id": "f056f42b-3792-49f3-841d-0f637c7c6683",
                "last_modified": 1460558483981
            }
        ]
    }

The *destination* collection metadata now contains the signature:

.. code-block:: bash

   $ http GET http://0.0.0.0:8888/v1/buckets/destination/collections/collection1 --auth user:pass

.. code-block:: javascript

   {
       "data": {
           "id": "collection1",
           "last_modified": 1460558496510,
           "signature": {
               "hash_algorithm": "sha384",
               "public_key": "MHYwEAYHKoZIzj0CAQYFK4EEACIDYgAE4k3FmG7dFoOt3Tuzl76abTRtK8sb/r/ibCSeVKa96RbrOX2ciscz/TT8wfqBYS/8cN4zMe1+f7wRmkNrCUojZR1ZKmYM2BeiUOMlMoqk2O7+uwsn1DwNQSYP58TkvZt6",
               "ref": "939wa3q3s3vn20rddhq8lb5ie",
               "signature": "oGkEfZOegNeYxHjDkc_TnUixX4BzESOzxd2OMn63rKBZL9FR3gjrRj7tmu8BWpnuWSLdH_aIjBsKsq4Dmg7XdDczeg86owSl5L-UYtKW3g4B4Yrh-yJZZFhchRbmZea6",
               "signature_encoding": "rs_base64url"
           }
       },
       "permissions": {
           "read": [
               "system.Everyone"
           ]
       }
   }


Generating a keypair
====================

To generate a new keypair, you can use the following command::

  $ python -m kinto_signer.generate_keypair private.pem public.pem


Running the tests
=================

To run the unit tests::

  $ make tests

For the functional tests, run these two services in separate terminals:

::

  $ make run-kinto

::

  $ make run-autograph

And start the test suite::

  $ make functional
