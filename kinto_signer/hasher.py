import copy
import hashlib
import json
import operator
import base64


def compute_hash(records):
    records = copy.deepcopy(records)
    records = filter(lambda r: r.get('deleted', False) is not True, records)
    records = sorted(records, key=operator.itemgetter('id'))

    serialized = json.dumps(records, sort_keys=True, separators=(',', ':'))
    h = hashlib.new('sha256')
    h.update(serialized)
    b64hash = base64.b64encode(h.digest())
    return b64hash
