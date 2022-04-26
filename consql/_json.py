import datetime
from decimal import Decimal

import orjson


def _default(o):
    if hasattr(o, 'json'):
        return o.json()
    if isinstance(o, datetime.date):
        return o.strftime('%F')
    if isinstance(o, datetime.time):
        return o.strftime('%T')
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, dict):
        return dict(o)
    if isinstance(o, set):
        return set(o)
    if isinstance(o, list):
        return list(o)
    if isinstance(o, tuple):
        return tuple(o)

    raise TypeError(
        f"Object of type '{o.__class__.__name__}' is not JSON serializable")

def dumps(obj, **kw):
    kw.pop('ensure_ascii', None)
    kw.setdefault('default', _default)
    kw.setdefault(
        'option',
        orjson.OPT_NON_STR_KEYS |
        orjson.OPT_PASSTHROUGH_SUBCLASS |
        orjson.OPT_PASSTHROUGH_DATACLASS |
        orjson.OPT_OMIT_MICROSECONDS |
        (orjson.OPT_INDENT_2 if kw.pop('indent', 0) else 0) |
        (orjson.OPT_SORT_KEYS if kw.pop('sort_keys', False) else 0)
    )

    result = orjson.dumps(obj, **kw)
    if isinstance(result, bytes):
        result = result.decode('utf-8')

    return result

def loads(s, **kw):
    return orjson.loads(s, **kw)
