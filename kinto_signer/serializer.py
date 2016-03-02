import copy
import json
import operator


def canonical_json(records):
    records = copy.deepcopy(records)
    records = filter(lambda r: r.get('deleted', False) is not True, records)
    records = sorted(records, key=operator.itemgetter('id'))

    return json.dumps(records, sort_keys=True, separators=(',', ':'))
