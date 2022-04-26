import datetime

import pytest
from libdev.codes import USER_STATUSES, LOCALES

from . import Base, Attribute, Table


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
        # coerce=coerces.date,
    )
    # tags=Attribute(
    #     types=list,
    #     required=True,
    #     default=lambda: [],
    #     tags='db_default',
    # )
    # extra=Attribute(
    #     types=Vars,
    #     required=False,
    #     default=lambda: {},
    #     coerce=Vars.coerce,
    #     always_coerce=True,
    #     tags='db_vars',
    # )
    # created=Attribute(
    #     types=datetime.datetime,
    #     required=False,
    #     default=now,
    #     coerce=coerces.date_time,
    # )
    # updated=Attribute(
    #     types=datetime.datetime,
    #     required=False,
    #     default=now,
    #     coerce=coerces.date_time,
    # )


@pytest.mark.asyncio
async def test_simple():
    user = User(
        id=1,
        login='kosyachniy',
        name='Alexey',
        surname='Poloz',
    )
    assert str(user)[:11] == "Object User"

    await user.save()

    # user = await User.load(1)
    # assert user.login == 'kosyachniy'

    # users = await User.list()
    # assert len(users.list) == 1

    # assert user.json() == {
    #     'id': 1,
    #     'status': 'authorized',
    #     'image': None,
    #     'login': 'kosyachniy',
    #     'name': 'Alexey',
    #     'surname': 'Poloz',
    #     'mail': None,
    #     'password': None,
    #     'phone': None,
    #     'lang': None,
    #     'birthday': None,
    # }

    await user.rm()
