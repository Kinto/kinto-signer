# -*- coding: utf-8 -*-
from kinto_signer import canonicaljson


def test_serialize_nan_and_infinity_as_null():
    assert canonicaljson.dumps(float("nan")) == "null"
    assert canonicaljson.dumps(float("inf")) == "null"
    assert canonicaljson.dumps(-float("inf")) == "null"


def test_uses_scientific_notation():
    samples = [
        (0, "0"),
        (0.00099, "0.00099"),
        (0.000011, "0.000011"),
        (0.0000011, "0.0000011"),
        (0.000001, "0.000001"),
        (0.00000099, "9.9e-7"),
        (0.0000001, "1e-7"),
        (0.000000930258908, "9.30258908e-7"),
        (0.00000000000068272, "6.8272e-13"),
        (10 ** 20, "100000000000000000000"),
        (10 ** 21, "1e+21"),
        # (10**15 + 0.1, "1000000000000000.1"),  # XXX: fails 1000000000000000.125
        (10 ** 16 * 1.1, "11000000000000000"),
        ("frequency at 10.0e+04", '"frequency at 10.0e+04"'),
    ]
    for number, string in samples:
        assert canonicaljson.dumps(number) == string


def test_uses_lowercase_unicode():
    records = [{"id": "4", "a": '"quoted"', "b": "Ich ♥ Bücher"}]
    assert (
        '{"a":"\\"quoted\\"","b":"Ich \\u2665 B\\u00fccher","id":"4"}]'
    ) in canonicaljson.dumps(records)


def test_escapes_quotes():
    records = [{"id": "4", "a": '"'}]
    assert '[{"a":"\\"","id":"4"}]' in canonicaljson.dumps(records)


def test_escapes_backslashes():
    records = [{"id": "4", "a": "This\\ this"}]
    assert '[{"a":"This\\\\ this","id":"4"}]' in canonicaljson.dumps(records)


def test_preserves_forwardslashes():
    records = [{"id": "4", "a": "image/jpeg"}]
    assert '[{"a":"image/jpeg","id":"4"}]' in canonicaljson.dumps(records)


def test_preserves_predefined_json_escapes():
    records = [{"id": "4", "a": "\n"}]
    assert '[{"a":"\\n","id":"4"}]' in canonicaljson.dumps(records)


def test_escapes_unicode_object_keys():
    records = [{"id": "4", "é": 1}]
    assert '[{"id":"4","\\u00e9":1}]' in canonicaljson.dumps(records)


def test_serializes_empty_object():
    records = [{"id": "4", "a": {}}]
    assert '[{"a":{},"id":"4"}]' in canonicaljson.dumps(records)


def test_serializes_empty_array():
    records = [{"id": "4", "a": []}]
    assert '[{"a":[],"id":"4"}]' in canonicaljson.dumps(records)


def test_serializes_empty_string():
    records = [{"id": "4", "a": ""}]
    assert '[{"a":"","id":"4"}]' in canonicaljson.dumps(records)


def test_serializes_none_to_null():
    records = [{"id": "4", "a": None}]
    assert '[{"a":null,"id":"4"}]' in canonicaljson.dumps(records)


def test_removes_spaces():
    records = [
        {"foo": "bar", "last_modified": "12345", "id": "1"},
        {"bar": "baz", "last_modified": "45678", "id": "2"},
    ]
    serialized = canonicaljson.dumps(records)
    assert " " not in serialized


def test_orders_object_keys():
    records = [{"a": "a", "id": "1", "b": "b"}]
    assert '[{"a":"a","b":"b","id":"1"}]' in canonicaljson.dumps(records)


def test_orders_nested_keys():
    records = [{"a": {"b": "b", "a": "a"}, "id": "1"}]
    assert '[{"a":{"a":"a","b":"b"},"id":"1"}]' in canonicaljson.dumps(records)


def test_orders_with_deeply_nested_dicts():
    records = [
        {
            "a": {
                "b": "b",
                "a": "a",
                "c": {
                    "b": "b",
                    "a": "a",
                    "c": ["b", "a", "c"],
                    "d": {"b": "b", "a": "a"},
                    "id": "1",
                    "e": 1,
                    "f": [2, 3, 1],
                    "g": {2: 2, 3: 3, 1: {"b": "b", "a": "a", "c": "c"}},
                },
            },
            "id": "1",
        }
    ]
    expected = (
        '[{"a":{"a":"a","b":"b","c":{"a":"a","b":"b","c":["b","a","c"],'
        '"d":{"a":"a","b":"b"},"e":1,"f":[2,3,1],"g":{'
        '"1":{"a":"a","b":"b","c":"c"},"2":2,"3":3},"id":"1"}},"id":"1"}]'
    )
    assert expected in canonicaljson.dumps(records)
