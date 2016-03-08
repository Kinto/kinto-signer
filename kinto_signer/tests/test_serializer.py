import json

from kinto_signer.serializer import canonical_json


def test_canonical_json_does_not_alter_records():
    records = [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]
    canonical_json(records)

    assert records == [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]


def test_canonical_json_preserves_data():
    records = [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]
    serialized = canonical_json(records)
    assert json.loads(serialized) == records


def test_canonical_json_removes_deleted_items():
    record = {'bar': 'baz', 'last_modified': '45678', 'id': '2'}
    deleted_record = {'deleted': True, 'last_modified': '12345', 'id': '1'}
    records = [
        deleted_record,
        record,
    ]
    serialized = canonical_json(records)
    assert [record] == json.loads(serialized)


def test_canonical_json_remove_spaces():
    records = [
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
    ]
    serialized = canonical_json(records)
    assert " " not in serialized


def test_canonical_json_orders_records_by_id():
    records = [
        {'bar': 'baz', 'last_modified': '45678', 'id': '2'},
        {'foo': 'bar', 'last_modified': '12345', 'id': '1'},
    ]
    serialized = json.loads(canonical_json(records))
    assert serialized[0]['id'] == '1'
    assert serialized[1]['id'] == '2'


def test_canonical_json_orders_object_keys():
    records = [{'a': 'a', 'c': 'c', 'b': 'b', 'id': '1'}]
    assert canonical_json(records) == '[{"a":"a","b":"b","c":"c","id":"1"}]'


def test_canonical_json_orders_nested_keys():
    records = [{'a': {'b': 'b', 'a': 'a'}, 'id': '1'}]
    assert canonical_json(records) == '[{"a":{"a":"a","b":"b"},"id":"1"}]'


def test_canonical_json_with_deeply_nested_dicts():
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
