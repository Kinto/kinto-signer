Kinto signer
############

|travis|

.. |travis| image:: https://travis-ci.org/Kinto/kinto-signer.svg?branch=master
    :target: https://travis-ci.org/Kinto/kinto-signer

.. |coveralls| image:: https://coveralls.io/repos/github/Kinto/kinto-signer/badge.svg?branch=master
    :target: https://coveralls.io/github/Kinto/kinto-signer?branch=master

**Kinto signer** is a `Kinto <https://kinto.readthedocs.io>`_ plugin
that introduces `digital signatures <https://en.wikipedia.org/wiki/Digital_signature>`_
in order to guarantee integrity and authenticity of collections of records.


How does it work?
=================

**Kinto signer** uses two collections:

* The *source*, where the authors create/update/delete records.
* The *destination*, where the clients obtain the records and their signature.

When the *source* collection metadata ``status`` is set to ``"to-sign"``, it will:

#. grab the whole list of records in this *source* collection
#. serialize it in a Canonical JSON form (*see below*)
#. compute a signature using the configured backend
#. update the *destination* collection records with the recent changes
#. update the *destination* collection metadata ``signature`` with the information
   obtain form the signature backend
#. set the *source* metadata ``status`` to ``"signed"``.

.. warning::

    The current implementation assumes the destination collection will be
    readable anonymously and won't be writable by anyone.
    (See `Kinto/kinto-signer#55 <https://github.com/Kinto/kinto-signer/issues/55>`_)

Content-Signature protocol
--------------------------

Kinto-signer produces signatures for the content of Kinto collections using
`ECDSA <https://fr.wikipedia.org/wiki/Elliptic_curve_digital_signature_algorithm>`_
with the P-384 strength.

* The content is prepended with ``Content-Signature:\x00`` prior to signing.
* The signature is produced with ECDSA on P-384 using SHA-384.
* The signature is returned as encoded using URL-safe variant of base-64.

See `Internet-Draft for P-384/ECDSA <https://github.com/martinthomson/content-signature/pull/2/files>`_

The content signature is validated in Firefox using the `Personal Security Manager <https://developer.mozilla.org/en/docs/Mozilla/Projects/PSM>`_.


Notes on canonical JSON
-----------------------

Specific to Kinto:

* Records are sorted by ascending ``id``
* Records with ``deleted: true`` are omitted

Standard canonical JSON:

* Object keys are sorted alphabetically
* No extra spaces in serialized content
* Double quotes are used
* Hexadecimal character escape sequences are used
* The alphabetical hexadecimal digits are lowercase
* Duplicate or empty properties are omitted

.. code-block:: python

    >>> canonical_json([{'id': '4', 'a': '"quoted"', 'b': 'Ich ♥ Bücher'},
                        {'id': '1', 'deleted': true},
                        {'id': '26', 'a': ''}])

    '[{"a":"","id":"26"},{"a":"\\"quoted\\"","b":"Ich \\u2665 B\\u00fccher","id":"4"}]'


* See `Internet-Draft Predictable Serialization for JSON Tools <http://webpki.org/ietf/draft-rundgren-predictable-serialization-for-json-tools-00.html>`_
* See `jsesc <https://github.com/mathiasbynens/jsesc>`_ to obtain similar output
  for escape sequences in JavaScript.


Setup
=====

To install this plugin in a Kinto server, a few configuration variables need
to be set.

Here is an example of what a configuration could look like:

.. code-block:: ini

  kinto.includes = kinto_signer

  kinto.signer.resources =
      /buckets/source/collections/collection1;/buckets/destination/collections/collection1
      /buckets/source/collections/collection2;/buckets/destination/collections/collection2

+---------------------------------+--------------------------------------------------------------------------+
| Setting name                    | What does it do?                                                         |
+=================================+==========================================================================+
| kinto.signer.resources          | The source collections URIs on which signatures should be triggered      |
|                                 | and the destination collection where the data and the signatures will    |
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


Multiple certificates
---------------------

Using above settings, every collections is signed with the same key.
But it is also possible to define multiple signers, per bucket or per collection.

Settings can be prefixed with bucket id:

```ini
kinto.signer.<bucket-id>.signer_backend = kinto_signer.signer.autograph
kinto.signer.<bucket-id>.autograph.server_url = http://172.11.20.1:8888
kinto.signer.<bucket-id>.autograph.hawk_id = bob
kinto.signer.<bucket-id>.autograph.hawk_secret = a-secret
```

Or prefixed with bucket and collection:

```ini
kinto.signer.<bucket-id>_<collection-id>.signer_backend = kinto_signer.signer.local_ecdsa
kinto.signer.<bucket-id>_<collection-id>.ecdsa.private_key = /path/to/private.pem
kinto.signer.<bucket-id>_<collection-id>.ecdsa.public_key = /path/to/public.pem
```


Usage
=====

Suppose we defined the following resources in the configuration:

.. code-block:: ini

    kinto.signer.resources = /buckets/source/collections/collection1;/buckets/destination/collections/collection1

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
               "content-signature": "x5u=https://bucket.example.net/appkey1.pem;p384ecdsa=Nv-EJ1D0fanElBGP4ZZmV6zu_b4DuCP3H7xawlLrcR7to3aKzqfZknVXOi94G_w8-wdKlysVWmhuDMqJqPcJV7ZudbhypJpj7kllWdPvMRZkoWXSfYLaoLMc8VQEqZcb",
               "x5u": "https://bucket.example.net/appkey1.pem",
           }
       },
       "permissions": {
           "read": [
               "system.Everyone"
           ]
       }
   }


Validating the signature
========================

With `kinto.js <https://github.com/Kinto/kinto.js/>`_, it is possible to define
incoming hooks that are executed when the data is retrieved from the server.

.. code-block:: javascript

    const kinto = new Kinto({
      remote: "https://mykinto.com/v1",
      bucket: "a-bucket"
    });
    const collection = kinto.collection("a-collection", {
      hooks: {
        "incoming-changes": [validateCollectionSignature]
      }});

.. code-block:: javascript

    function validateCollectionSignature(payload, collection) {
      // 1 - Fetch signature from collection endpoint
      // 2 - Fetch public key certificate
      // 3 - Merge incoming changes with local records
      // 4 - Serialize as canonical JSON
      // 5 - Verify the signature against the content with the public key
      // 6 - Return `payload` if valid, throw error otherwise.
    }

The content of the ``demo/`` folder implements the signature verification with
kinto.js and the WebCrypto API. It is `published online <https://kinto.github.io/kinto-signer/>`_
but relies on a semi-public server instance.

See also `the complete integration within Firefox <https://bugzilla.mozilla.org/show_bug.cgi?id=1263602>`_
using the `Network Security Services <https://developer.mozilla.org/en-US/docs/Mozilla/Projects/NSS/Overview>`_.


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
