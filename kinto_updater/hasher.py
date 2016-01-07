import copy
import hashlib
import json
import operator


def compute_hash(records):
    records = copy.deepcopy(records)
    for record in records:
        if 'last_modified' in record.keys():
            del record['last_modified']

    records = filter(lambda r: r.get('deleted', False) is not True, records)
    records = sorted(records, key=operator.itemgetter('id'))

    serialized = json.dumps(records, sort_keys=True)
    h = hashlib.new('sha256')
    h.update(serialized)
    return h.hexdigest()
