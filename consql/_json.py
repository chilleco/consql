"""
JSON handler
"""

# pylint: disable=no-member,missing-function-docstring
# pylint: disable=too-many-return-statements

import datetime
from decimal import Decimal

import orjson


def _default(value):
    if hasattr(value, 'json'):
        return value.json()
    if isinstance(value, datetime.date):
        return value.strftime('%F')
    if isinstance(value, datetime.time):
        return value.strftime('%T')
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, set):
        return set(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return tuple(value)

    raise TypeError(
        f"Object of type '{value.__class__.__name__}' is not JSON serializable")

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

def loads(data, **kw):
    return orjson.loads(data, **kw)
