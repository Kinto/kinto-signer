import copy
import hashlib
import json
import operator
import base64


def canonical_json(records):
    records = copy.deepcopy(records)
    records = filter(lambda r: r.get('deleted', False) is not True, records)
    records = sorted(records, key=operator.itemgetter('id'))

    return json.dumps(records, sort_keys=True, separators=(',', ':'))


def compute_hash(string):
    h = hashlib.new('sha256')
    h.update(string.encode('utf-8'))
    b64hash = base64.b64encode(h.digest())
    return b64hash
