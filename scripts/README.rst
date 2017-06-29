Kinto Signer CLI tools
======================

canonical_json script
---------------------

The ``canonical_json.py`` script allow you to present a json file in a
way that allow you to diff JSON files.

All keys are recursively sorted and the presentation is set to an
indentation of two spaces.

Using STDIN and STDOUT
++++++++++++++++++++++

.. code-block::

   $ python canonical_json.py <<EOF
   {"mum": "Agnes", "dad": "Pascal"}
   EOF
   {
     "dad": "Pascal", 
     "mum": "Agnes"
   }

Using a file as input
+++++++++++++++++++++

.. code-block::

   $ python canonical_json.py parents.json
   {
     "dad": "Pascal", 
     "mum": "Agnes"
   }

Using a file as input and output
++++++++++++++++++++++++++++++++

.. code-block::

   $ python canonical_json.py parents.json canonical_parents.json
