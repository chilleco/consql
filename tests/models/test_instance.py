import json
import datetime

import pytest
from libdev.codes import USER_STATUSES, LOCALES
from libdev.gen import generate

from . import Base, Attribute, Table, Extra
from consql import coerces


def coerce_list(value):
    if isinstance(value, str):
        value = json.loads(value)

    result = []

    if isinstance(value, (list, tuple)):
        for item in value:
            result.append(json.loads(item) if isinstance(item, str) else item)

    return result


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
    options = Attribute(
        types=(list, tuple),
        required=True,
        default=lambda: [],
        coerce=coerce_list,
        always=True,
        tags='db_json',
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
    # Entity
    user_login = generate()
    user = User(
        login=user_login,
        name='Alexey',
        surname='Poloz',
    )
    assert str(user)[:11] == "Object User"

    # Create
    await user.save()
    user_id = user.id
    assert isinstance(user_id, int)

    # Conditions
    users, _ = await User.get(conditions=[
        ('login', user_login),
    ])
    assert len(users) == 1

    users, _ = await User.get(conditions=[
        ('login', generate()),
    ])
    assert len(users) == 0

    # By primary key
    user = await User.get(user_id)
    assert user.id == user_id
    assert user.login == user_login
    assert user.name == 'Alexey'

    # By specific key
    user = await User.get(user_login, by='login')
    assert isinstance(user, User)

    # Edit
    user.name = 'Alex'
    await user.save()

    # Reload
    await user.reload()
    assert user.name == 'Alex'

    # Pager list
    users = await User.get(offset=1)
    assert len(users) >= 1

    # Cursor list
    users, cursor = await User.get()
    users_count = len(users)
    assert users_count >= 1
    assert cursor

    # Create
    user_login = generate()
    user_created = datetime.datetime.now() - datetime.timedelta(days=1)
    user = User(
        login=user_login,
        name='Evgeniy',
        surname='Zaycev',
        extra={-12: "белый"},
        created=user_created,
    )
    await user.save()

    # JSON
    assert user.json() == {
        'id': user_id+1, # increment key
        'status': 'authorized', # default value
        'image': None,
        'login': user_login,
        'name': 'Evgeniy',
        'surname': 'Zaycev',
        'mail': None,
        'password': None,
        'phone': None,
        'lang': None,
        'birthday': None,
        'tags': [],
        'extra': {'-12': "белый"}, # int key → str
        'options': [],
        'created': user_created, # specified value
        'updated': user.updated, # automatic value
    }

    # Remove
    await user.rm()
    user = await User.get(user_id)
    await user.rm()
    users, cursor = await User.get()
    assert len(users) == users_count - 1

    # RAW fetch
    user = User(
        login=generate(),
        name='Alex',
        surname='Polo',
    )
    await user.save()
    assert (await User.fetch('count'))[0]['count'] > 0
    assert (await User.fetch('count', conditions=[
        ('name', 'Alex'),
    ]))[0]['count'] > 0
    assert (await User.fetch('count', conditions=[
        ('name', 'Ivan'),
    ]))[0]['count'] == 0
