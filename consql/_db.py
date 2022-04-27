"""
Database
"""

import asyncio
import random
import sys
import copy
import re
import ssl

from libdev.cfg import cfg
import asyncpg
from asyncpg.connection import Connection
from asyncpg.exceptions import InterfaceError, PostgresConnectionError
from asyncpg.pool import Pool, PoolConnectionProxy

from .errors import ErrorWrong


PG_DEFAULT_DB = 'main'
DBS = {
    'main': {
        'migrations': 'db/postgresql/main',
        'shards': [{
            'host': f"{cfg('pg.host')}:{cfg('pg.port')}",
            'dbname': cfg('pg.db'),
            'user': cfg('pg.user'),
            'password': cfg('pg.pass')
        }],
        'recheck_timeout': 15,
        'pool_min_size': 10,
        'pool_max_size': 10,
        'pool_max_queries': 5000,
        'pool_connection_ttl': 300,
        'nshards': 1,
        'metric_suffix': {
            'env': 'PGPOOL_METRIC_SUFFIX',
        },
        'shard_schema': {
            'version': 1,
            'module': 'consql.shard_schema',
            'next_version': None,
            'gap_version': None,
        }
    },
}
CHECK_QUERY = '''SELECT pg_is_in_recovery() AS "replica", COALESCE(
    EXTRACT(epoch FROM NOW() - pg_last_xact_replay_timestamp()), 0) AS "lag"
'''


class PgDsnParser:
    REQUIRED_DSN_FIELDS = ('host', 'port', 'dbname', 'user', 'password')
    hosts: list

    def __init__(self, dsnstr):
        if isinstance(dsnstr, str):
            dsn = map(lambda x: re.split('=', x, 1), re.split(r'\s+', dsnstr))
            dsn = dict(dsn)
        else:
            dsn = dsnstr

        dsn.setdefault('host', 'localhost')
        dsn.setdefault('port', '5432')
        for name in self.REQUIRED_DSN_FIELDS:
            if name not in dsn:
                raise RuntimeError(
                    'no "%s" field in dsn: "%s"' % (name, dsnstr)
                )

        dsn['host'] = dsn['host'].split(',')

        self.hosts = []

        for host in dsn['host']:
            host = host.strip()
            hostdsn = copy.copy(dsn)
            hostdsn['host'] = host

            if re.match(r'^\S+:\d+$', host):
                host, port = host.rsplit(':', 1)
                hostdsn['host'] = host
                hostdsn['port'] = port

            self.hosts.append(hostdsn)

    def as_dict(self, hostno):
        host = self.hosts[hostno]

        connect_kwargs = {
            'host': host['host'],
            'port': host['port'],
            'database': host['dbname'],
            'user': host['user'],
            'password': host['password'],
        }

        if 'sslmode' in host and host['sslmode']:
            if host['sslmode'] == 'disable':
                connect_kwargs['ssl'] = False
            elif host['sslmode'] == 'require':
                sslctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                sslctx.check_hostname = False
                sslctx.verify_mode = ssl.CERT_NONE
                connect_kwargs['ssl'] = sslctx

        return connect_kwargs

class PgShardConnectionContext:
    __slots__ = ('pgshard', 'mode', 'pool', 'conn',)

    def __init__(self, pgshard, mode):
        self.pgshard = pgshard
        self.mode = mode
        self.pool = None
        self.conn = None

    async def __aenter__(self):
        self.pool, self.conn = await self.pgshard.acquire(self.mode)

        return self.conn

    async def __aexit__(self, extype, extvalue, extraceback):
        pool, conn = self.pool, self.conn
        self.pool, self.conn = None, None

        await pool.release(conn)

class PgShardConnection(Connection):
    hostno = 0
    mode = 'not_connected'
    shardno = 0
    name = None

    def __repr__(self):
        return '<PgShardConnection[{}].{}#{}>'.format(
            self.name, self.mode, self.shardno,
        )

class PgShard:
    query_last_time = 0
    check_last_time = 0
    check_interval = 10
    check_sleep = 0.5
    check_is_running = False
    check_task = None

    slow_lag = 25

    def __init__(self, dsnstr, *, name=None, shardno=0, loop=None, **opts):
        self.dsnstr = dsnstr
        self.dsn = PgDsnParser(dsnstr)
        self.name = name or self.dsn.hosts[0]['dbname']
        self.shardno = shardno
        self.loop = loop
        self.lock = asyncio.Lock()
        self.pool_min_size = opts.get('pool_min_size', 10)
        self.pool_max_size = opts.get('pool_max_size', 10)
        self.pool_max_queries = opts.get('pool_max_queries', 5000)
        self.pool_idle_connection_ttl = opts.get(
            'pool_idle_connection_ttl', 60,
        )
        self.pool_timeout = opts.get('pool_timeout', 5)
        self.pool_acquire_timeout = opts.get('pool_acquire_timeout', 5)
        self.pool_query_timeout = opts.get('pool_query_timeout', 15)
        self.stat = {}

        for hostno, _ in enumerate(self.dsn.hosts):
            self.stat[hostno] = {
                'no': hostno,
                'host': self.dsn.hosts[hostno]['host'],
                'port': self.dsn.hosts[hostno]['port'],
                'shardno': self.shardno,
                'db': self.name,
                'pool': None,
                'mode': 'not_connected',
                'inited': False,
            }

    def __repr__(self):
        return '<PgShard.{name}[{shardno}] {id:#x}>'.format(
            name=self.name,
            shardno=self.shardno,
            id=id(self),
        )

    def __call__(self, *, mode: str = 'master') -> PgShardConnectionContext:
        return PgShardConnectionContext(self, mode)

    @property
    def is_connected(self) -> bool:
        for stat_host in self.stat.values():
            if stat_host['mode'] == 'master':
                return True

        return False

    async def acquire(self,  mode):
        """ Get connection from the pool """

        await self._loop_changed()

        self.query_last_time = self.loop.time()

        async with self.lock:
            if (
                not self.check_is_running
                or self.check_task is None
                or self.check_task.done()
            ):
                self.check_is_running = True
                await self._check()
                self.check_task = asyncio.create_task(self._run_check())
        try:
            stat_host = await self._seek_pool(mode)
        except ErrorWrong:
            self.check_last_time = 0
            raise

        try:
            pool = stat_host['pool']
            conn = await pool.acquire(timeout=self.pool_acquire_timeout)

            realcon = conn._con
            realcon.hostno = stat_host['no']
            realcon.shardno = stat_host['shardno']
            realcon.name = stat_host['db']
            realcon.mode = stat_host['mode']

            return pool, conn

        except (
            OSError,
            ConnectionError,
            asyncio.TimeoutError,
            PostgresConnectionError,
            InterfaceError,
        ):
            if mode != 'master':
                stat_host['mode'] = 'not_connected'

            self.check_last_time = 0

            raise

    async def close(self, *, force: bool = False) -> None:
        await self._loop_changed()

        async with self.lock:
            self.check_is_running = False

            if self.check_task:
                try:
                    await self.check_task
                    self.check_task = None
                except Exception as exc:
                    pass

            await asyncio.gather(
                *(
                    self._close_pool(hostno, force=force)
                    for hostno, _ in enumerate(self.dsn.hosts)
                ),
                return_exceptions=False,
            )

    async def _run_check(self) -> None:
        while self.check_is_running:
            await self._check()
            await asyncio.sleep(self.check_sleep)

    async def _check(self) -> None:
        t = self.loop.time()

        if self.is_connected:
            if t - self.check_last_time < self.check_interval:
                return

            if t - self.query_last_time > self.check_interval:
                return

        await asyncio.gather(
            *(
                self._check_pool(hostno)
                for hostno, _ in enumerate(self.dsn.hosts)
            ),
            return_exceptions=True,
        )

        if self.is_connected:
            self.check_last_time = t

    async def _check_pool(self, hostno: int) -> None:
        await self._loop_changed()

        stat_host = self.stat[hostno]

        pool = stat_host['pool']
        mode = stat_host['mode']

        server_settings = {
            'enable_seqscan': 'off',
            'enable_bitmapscan': 'off',
            'enable_sort': 'off',
        } if 'pytest' in sys.modules else {}

        if not isinstance(pool, Pool):
            try:
                pool = await asyncpg.create_pool(
                    min_size=self.pool_min_size,
                    max_size=self.pool_max_size,
                    max_queries=self.pool_max_queries,
                    max_inactive_connection_lifetime=(
                        self.pool_idle_connection_ttl
                    ),
                    connection_class=PgShardConnection,
                    timeout=self.pool_timeout,
                    command_timeout=self.pool_query_timeout,
                    server_settings=server_settings,
                    **self.dsn.as_dict(hostno),
                )
            except (
                    OSError,
                    ConnectionError,
                    asyncio.TimeoutError,
            ):
                new_mode = 'not_connected'

        if isinstance(pool, Pool):
            try:
                async with pool.acquire(timeout=5) as check_conn:
                    check_result = await check_conn.fetchrow(
                        CHECK_QUERY, timeout=5,
                    )

                    if check_result['replica']:
                        if check_result['lag'] > self.slow_lag:
                            new_mode = 'slow'
                        else:
                            new_mode = 'slave'
                    else:
                        new_mode = 'master'

            except (
                    OSError,
                    ConnectionError,
                    asyncio.TimeoutError,
                    PostgresConnectionError,
                    InterfaceError,
            ):
                new_mode = 'not_connected'

        stat_host['pool'] = pool
        stat_host['mode'] = new_mode
        stat_host['inited'] = True

        if new_mode == mode:
            return

        if new_mode == 'not_connected':
            return

    async def _seek_pool(self, mode):
        candidates = []

        for stat_host in self.stat.values():
            if stat_host['mode'] == mode:
                candidates.append(stat_host)

        if candidates:
            return random.choice(candidates)

        if mode == 'master':
            raise ErrorWrong(
                f'Master exception {self.name}: {self.shardno}: {mode}'
            )

        if mode == 'slave':
            return await self._seek_pool('master')

        if mode == 'slow':
            return await self._seek_pool('slave')

        return await self._seek_pool('slow')

    async def _close_pool(self, hostno: int, *, force: bool = False) -> None:
        await self._loop_changed()

        stat_host = self.stat[hostno]
        pool = stat_host['pool']

        try:
            if isinstance(pool, Pool):
                if force:
                    pool.terminate()
                else:
                    await pool.close()
        except Exception:
            pass
        finally:
            stat_host['pool'] = None
            stat_host['mode'] = 'not_connected'
            stat_host['inited'] = False

    async def _loop_changed(self) -> bool:
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

        if 'pytest' not in sys.modules:
            return False

        loop = asyncio.get_event_loop()

        if id(loop) == id(self.loop):
            return False

        self.loop = loop
        self.lock = asyncio.Lock()

        self.check_is_running = False

        for stat_host in self.stat.values():
            stat_host['pool'] = None
            stat_host['mode'] = 'not_connected'
            stat_host['inited'] = False
        self.check_task = None

        return True


class PgShards:
    shards: list
    _name = None

    def __init__(self, dsnstrs, *, name=None, nshards=None, **opts):
        self._name = name
        shards = []

        for shardno, dsnstr in enumerate(dsnstrs):
            shard = PgShard(
                dsnstr,
                name=name,
                shardno=shardno,
                **opts,
            )

            shards.append(shard)

        self.shards = shards
        if nshards is None:
            nshards = len(shards)
        self._nshards = nshards

    @property
    def name(self):
        if self._name is not None:
            return self._name
        return self.shards[0].name

    def __call__(self, *, shard=None, mode='master', key=None, eid=None):
        if shard is None:
            shard = 0

        if shard < 0 or shard >= len(self.shards):
            raise ErrorWrong(f'Shard count {shard} (to {len(self.shards) - 1})')

        shardo = self.shards[shard]
        return shardo(mode=mode)

    async def close(self):
        for shard in self.shards:
            await shard.close()

    @property
    def nshards(self):
        return self._nshards

class Dbh:
    default_database: str

    def __init__(self):
        self.default_database = PG_DEFAULT_DB

        for dbname, dbcfg in DBS.items():
            shards = list(filter(lambda x: x, DBS['main']['shards']))

            if not shards:
                continue

            setattr(
                self,
                dbname,
                PgShards(shards, name=dbname, **dbcfg)
            )

    def __call__( self, *, db=None, mode='master', shard=None):
        if not db:
            db = self.default_database

        if not hasattr(self, db):
            raise ValueError(f'Unknown database: {db}')

        shards = getattr(self, db)
        return shards(mode=mode, shard=shard)

    def nshards(self, db: str):
        if not hasattr(self, db):
            raise ValueError(f'Unknown database: {db}')

        dbshards = getattr(self, db)
        return dbshards.nshards

    async def close(self):
        for dbname in DBS.keys():
            shards = getattr(self, dbname)
            await shards.close()


dbh = Dbh()
