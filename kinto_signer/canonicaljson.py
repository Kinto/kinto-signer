import json
import re
from json import encoder as json_encoder


__all__ = ["dumps"]


def numberstr(o):
    """
    Mimic JavaScript Number#toString()
    """
    if o != o or o == json_encoder.INFINITY or o == -json_encoder.INFINITY:
        return "null"
    elif 0 < o < 10 ** -6 or o >= 10 ** 21:
        fnative = format(o, ".8e")
        # 1.0e-04 --> 1e-4
        return re.sub(r"(\.?0*)e([\-+])0?", r"e\2", fnative)
    fnative = format(o, ".8f").lstrip()
    # 23.0 --> 23
    return re.sub(r"\.?0+$", "", fnative)


class FloatEncoder(json.JSONEncoder):
    def iterencode(self, o, _one_shot=False):
        # Rip-off from repo of CPython 3.7.1
        # https://github.com/python/cpython/blob/v3.7.1/Lib/json/encoder.py#L204-L257
        markers = None
        _encoder = json_encoder.encode_basestring_ascii
        _iterencode = json_encoder._make_iterencode(
            markers,
            self.default,
            _encoder,
            self.indent,
            numberstr,
            self.key_separator,
            self.item_separator,
            self.sort_keys,
            self.skipkeys,
            _one_shot,
            _intstr=numberstr,
        )
        return _iterencode(o, 0)


def dumps(source):
    return json.dumps(source, sort_keys=True, separators=(",", ":"), cls=FloatEncoder)
