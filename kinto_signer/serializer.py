import json
import operator


def canonical_json(records, last_modified):
    records = (r for r in records if not r.get('deleted', False))
    records = sorted(records, key=operator.itemgetter('id'))

    payload = {'data': records, 'last_modified': '%s' % last_modified}

    return json.dumps(payload, sort_keys=True, separators=(',', ':'))
