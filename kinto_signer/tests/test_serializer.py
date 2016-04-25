# -*- coding: utf-8 -*-
import json

from kinto_signer.serializer import canonical_json

#
# Kinto specific
#


def test_orders_records_by_id():
    records = [
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
    ]
    serialized = json.loads(canonical_json(records))
    assert serialized[0]['id'] == '1'
    assert serialized[1]['id'] == '2'


def test_removes_deleted_items():
    record = {'bar': 'baz', 'last_modified': '45678', 'id': '2'}
    deleted_record = {'deleted': True, 'last_modified': '12345', 'id': '1'}
    records = [
        deleted_record,
        record,
    ]
    serialized = canonical_json(records)
    assert [record] == json.loads(serialized)

#
# Standard
#


def test_does_not_alter_records():
    records = [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]
    canonical_json(records)

    assert records == [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]


def test_preserves_data():
    records = [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]
    serialized = canonical_json(records)
    assert json.loads(serialized) == records


def test_uses_lowercase_unicode():
    records = [{'id': '4', 'a': '"quoted"', 'b': 'Ich ♥ Bücher'},
               {'id': '26', 'd': None, 'a': ''}]
    assert canonical_json(records) == (
        '[{"a":"","d":null,"id":"26"},'
        '{"a":"\\"quoted\\"","b":"Ich \\u2665 B\\u00fccher","id":"4"}]')


def test_escapes_quotes():
    records = [{'id': '4', 'a': "\""}]
    assert canonical_json(records) == '[{"a":"\\"","id":"4"}]'


def test_escapes_backslashes():
    records = [{'id': '4', 'a': "This\\and this"}]
    assert canonical_json(records) == '[{"a":"This\\\\and this","id":"4"}]'


def test_preserves_forwardslashes():
    records = [{'id': '4', 'a': "image/jpeg"}]
    assert canonical_json(records) == '[{"a":"image/jpeg","id":"4"}]'


def test_preserves_predefined_json_escapes():
    records = [{'id': '4', 'a': "\n"}]
    assert canonical_json(records) == '[{"a":"\\n","id":"4"}]'


def test_escapes_unicode_object_keys():
    records = [{'id': '4', 'é': 1}]
    assert canonical_json(records) == '[{"id":"4","\\u00e9":1}]'


def test_serializes_empty_object():
    records = [{'id': '4', 'a': {}}]
    assert canonical_json(records) == '[{"a":{},"id":"4"}]'


def test_serializes_empty_array():
    records = [{'id': '4', 'a': []}]
    assert canonical_json(records) == '[{"a":[],"id":"4"}]'


def test_serializes_empty_string():
    records = [{'id': '4', 'a': ''}]
    assert canonical_json(records) == '[{"a":"","id":"4"}]'


def test_serializes_none_to_null():
    records = [{'id': '4', 'a': None}]
    assert canonical_json(records) == '[{"a":null,"id":"4"}]'


def test_removes_spaces():
    records = [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]
    serialized = canonical_json(records)
    assert " " not in serialized


def test_orders_object_keys():
    records = [{'a': 'a', 'c': 'c', 'b': 'b', 'id': '1'}]
    assert canonical_json(records) == '[{"a":"a","b":"b","c":"c","id":"1"}]'


def test_orders_nested_keys():
    records = [{'a': {'b': 'b', 'a': 'a'}, 'id': '1'}]
    assert canonical_json(records) == '[{"a":{"a":"a","b":"b"},"id":"1"}]'


def test_orders_with_deeply_nested_dicts():
    records = [{
        'a': {
            'b': 'b',
            'a': 'a',
            'c': {
                'b': 'b',
                'a': 'a',
                'c': ['b', 'a', 'c'],
                'd': {'b': 'b', 'a': 'a'},
                'id': '1',
                'e': 1,
                'f': [2, 3, 1],
                'g': {2: 2, 3: 3, 1: {
                    'b': 'b', 'a': 'a', 'c': 'c'}}}},
        'id': '1'}]
    expected = (
        '[{"a":{"a":"a","b":"b","c":{"a":"a","b":"b","c":["b","a","c"],'
        '"d":{"a":"a","b":"b"},"e":1,"f":[2,3,1],"g":{'
        '"1":{"a":"a","b":"b","c":"c"},"2":2,"3":3},"id":"1"}},"id":"1"}]')
    assert canonical_json(records) == expected
