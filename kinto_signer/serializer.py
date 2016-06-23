import copy
import json
import operator


def canonical_json(records, last_modified):
    records = copy.deepcopy(records)
    records = filter(lambda r: r.get('deleted', False) is not True, records)
    records = sorted(records, key=operator.itemgetter('id'))

    payload = {'data': records, 'last_modified': '%s' % last_modified}

    return json.dumps(payload, sort_keys=True, separators=(',', ':'))
