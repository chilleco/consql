import os
from os.path import isfile
import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='password',
        database='main',
    )

    migrations = sorted([f for f in os.listdir() if not isfile(f)])

    for migration in migrations:
        if any(f not in {'up.sqlt', 'down.sqlt'} for f in os.listdir()):
            continue

        with open(f'{migration}/down.sql', 'r') as file:
            data = file.read()
        try:
            await conn.fetch(data)
        except Exception as e:
            print(e)

        with open(f'{migration}/up.sql', 'r') as file:
            data = file.read()
        await conn.fetch(data)


asyncio.run(main())
