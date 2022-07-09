import pytest
from libdev.gen import generate

from tests.models.test_instance import User


@pytest.mark.asyncio
async def test_simple():
    # Pager
    await User(login=generate()).save()
    users = await User.get(offset=0)
    assert len(users) >= 1

    # Full
    for _ in range(100):
        await User(login=generate()).save()
    users, cursor = await User.get(direction='ASC')
    assert len(users) > 100

    # Cursor
    for _ in range(2):
        await User(login=generate()).save()
    users, _ = await User.get(cursor=cursor)
    assert len(users) == 2

    # # Custom
    # login = generate()
    # user = User(
    #     login=login,
    #     options=[
    #         ('S', 'blue'),
    #         ('M', 'black'),
    #         ('L', 'beige'),
    #     ],
    # )
    # await user.save()
    # users = await User.get(
    #     by='custom',
    #     offset=0,
    #     conditions=('login', login),
    #     # option=('M', 'black'),
    # )
    # assert len(users) == 1
    # assert users[0].id == user.id
