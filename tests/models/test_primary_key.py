import datetime

import pytest

from . import Base, Attribute, Table
from consql import coerces


class Priority(Base, table=Table('priorities', pkey=('category', 'brand', 'sex'))):
    category = Attribute(types=int, required=True)
    brand = Attribute(types=int, required=True)
    sex = Attribute(types=str, required=True)
    status = Attribute(types=int, required=False)
    created = Attribute(
        types=datetime.datetime,
        required=False,
        default=coerces.now,
        coerce=coerces.date_time,
    )
    updated = Attribute(
        types=datetime.datetime,
        required=False,
        default=coerces.now,
        coerce=coerces.date_time,
    )


@pytest.mark.asyncio
async def test_simple():
    priority = Priority(
        category=1,
        brand=1,
        sex='male',
        status=1,
    )
    assert str(priority)[:15] == "Object Priority"

    await priority.save()
