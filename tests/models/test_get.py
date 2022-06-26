import datetime

import pytest
from libdev.codes import USER_STATUSES, LOCALES
from libdev.gen import generate

from . import Base, Attribute, Table, Extra
from consql import coerces


class User(Base, table=Table('users')):
    id = Attribute(types=int, required=False)
    status = Attribute(
        types=str,
        required=True,
        default='authorized',
        enum=USER_STATUSES,
    )
    image = Attribute(types=str, required=False)
    login = Attribute(types=str, required=False)
    name = Attribute(types=str, required=False)
    surname = Attribute(types=str, required=False)
    mail = Attribute(types=str, required=False)
    password = Attribute(types=str, required=False)
    phone = Attribute(types=int, required=False)
    lang = Attribute(
        types=str,
        required=False,
        enum=LOCALES,
    )
    birthday = Attribute(
        types=datetime.date,
        required=False,
        coerce=coerces.date,
    )
    tags = Attribute(
        types=list,
        required=True,
        default=lambda: [],
        tags='db_default',
    )
    extra = Attribute(
        types=Extra,
        required=False,
        default=lambda: {},
        coerce=Extra.coerce,
        always=True,
        tags='db_extra',
    )
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
    # Full
    for _ in range(100):
        await User(login=generate()).save()

    users, cursor = await User.get()
    print(len(users), cursor)

    # Pager

    # Cursor
