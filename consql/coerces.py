import re
import datetime
from dateutil.parser import parse


def now():
    return datetime.datetime.now().replace(microsecond=0)

def now_min():
    return datetime.datetime.now().replace(microsecond=0, second=0)

def time2time(value):
    if value is None:
        return None
    elif value == '':
        return None
    elif isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value)
        except ValueError:
            try:
                result_ru = re.search(
                    r'^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(.*)$',
                    value,
                )
                if result_ru:
                    day = int(result_ru.group(1))
                    month = int(result_ru.group(2))
                    year = int(result_ru.group(3))
                    times = result_ru.group(4)

                    value = '%04d-%02d-%02d' % (year, month, day)
                    if times:
                        value += 'T' + times

                    value = parse(value)

                elif re.search(r'^\d{1,2}:', value):
                    value = parse(value)
                    value = datetime.datetime.combine(
                        now().date(),
                        value.time(),
                    )
                else:
                    value = parse(value)

            except (ValueError, OverflowError):
                return None

    elif isinstance(value, (float, int)):
        value = datetime.datetime.fromtimestamp(value)

    if isinstance(value, (datetime.datetime, datetime.time)):
        value = value.replace(microsecond=0)

    return value

def date_time(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime.datetime):
        return value

    if isinstance(value, (float, int)):
        return datetime.datetime.fromtimestamp(value)

    if isinstance(value, str):
        value = time2time(value)
        if value:
            return value

    raise ValueError(f'Unknown datetime "{value}"')

def date_time_min(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime.datetime):
        return value

    if isinstance(value, (float, int)):
        return datetime.datetime.fromtimestamp(value)

    if isinstance(value, str):
        value = time2time(value)
        if value:
            return value

    raise ValueError(f'Unknown datetime "{value}"')

def date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime.date):
        return value

    return date_time(value).date()

def time(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime.time):
        return value

    return date_time(value).time()

def timedelta(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime.timedelta):
        return value
    if not isinstance(value, dict):
        raise ValueError('timedelta value must be dict')

    return datetime.timedelta(**value)
