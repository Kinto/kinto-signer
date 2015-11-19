import copy
import hashlib
import json
import operator


def compute_hash(records):
    records = copy.deepcopy(records)
    for record in records:
        if 'last_modified' in record.keys():
            del record['last_modified']

    records = sorted(records, key=operator.itemgetter('id'))

    serialized = json.dumps(records, sort_keys=True)
    print(serialized)
    h = hashlib.new('sha256')
    h.update(serialized)
    return h.hexdigest()
