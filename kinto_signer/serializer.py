import re
import json
import operator


def canonical_json(records, last_modified):
    records = (r for r in records if not r.get('deleted', False))
    records = sorted(records, key=operator.itemgetter('id'))

    payload = {'data': records, 'last_modified': '%s' % last_modified}

    dump = json.dumps(payload, sort_keys=True, separators=(',', ':'))

    # Fix scientific notations of Python JSON to conform with ECMAScript v6
    # 9.30258908e-07 --> 9.30258908e-7
    dump = dump.replace("e-0", "e-")

    return dump
