import asyncio
import json

import pytest
from aiohttp.test_utils import teardown_test_loop
from atoolbox.test_utils import DummyServer, create_dummy_server

from em2.main import create_app
from em2.settings import Settings


def pytest_addoption(parser):
    parser.addoption('--reuse-db', action='store_true', default=False, help='keep the existing database if it exists')


settings_args = dict(
    DATABASE_URL='postgres://postgres@localhost:5432/em2_testing',
    REDISCLOUD_URL='redis://localhost:6379/6',
    bcrypt_work_factor=6,
    max_request_size=1024 ** 2,
)


@pytest.fixture(scope='session', name='settings_session')
def _fix_settings_session():
    return Settings(**settings_args)


@pytest.fixture(scope='session', name='clean_db')
def _fix_clean_db(request, settings_session):
    # loop fixture has function scope so can't be used here.
    from atoolbox.db import prepare_database

    loop = asyncio.new_event_loop()
    loop.run_until_complete(prepare_database(settings_session, True))
    teardown_test_loop(loop)


@pytest.fixture(name='dummy_server')
async def _fix_dummy_server(loop, aiohttp_server):
    return await create_dummy_server(aiohttp_server)


replaced_url_fields = ('grecaptcha_url',)


@pytest.fixture(name='settings')
def _fix_settings(dummy_server: DummyServer, request, tmpdir):
    return Settings(**{f: f'{dummy_server.server_name}/{f}/' for f in replaced_url_fields}, **settings_args)


@pytest.fixture(name='db_conn')
async def _fix_db_conn(loop, settings, clean_db):
    from buildpg import asyncpg

    conn = await asyncpg.connect_b(dsn=settings.pg_dsn, loop=loop)

    tr = conn.transaction()
    await tr.start()

    yield conn

    await tr.rollback()
    await conn.close()


@pytest.yield_fixture
async def redis(loop, settings):
    addr = settings.redis_settings.host, settings.redis_settings.port
    from aioredis import create_redis

    redis = await create_redis(addr, db=settings.redis_settings.database, loop=loop)
    await redis.flushdb()

    yield redis

    redis.close()
    await redis.wait_closed()


async def pre_startup_app(app):
    from atoolbox.db.helpers import SimplePgPool

    app['pg'] = SimplePgPool(app['test_conn'])


@pytest.fixture(name='cli')
async def _fix_cli(settings, db_conn, aiohttp_client, redis, loop):
    app = await create_app(settings=settings)
    app['test_conn'] = db_conn
    app.on_startup.insert(0, pre_startup_app)
    cli = await aiohttp_client(app)

    async def post_json(url, data, *, origin=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data)

        return await cli.post(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Referer': f'http://127.0.0.1:{cli.server.port}/dummy-referer/',
                'Origin': origin or f'http://127.0.0.1:{cli.server.port}',
            },
        )

    cli.post_json = post_json
    return cli


@pytest.fixture(name='url')
def _fix_url(cli):
    def f(name, *, query=None, **kwargs):
        # TODO if this is used in main code base it should be moved there and reused.
        try:
            app_name, route_name = name.split(':')
        except ValueError:
            raise RuntimeError('not app name, use format "<app name>:<route name>"')

        try:
            app = cli.server.app[app_name + '_app']
        except KeyError:
            raise RuntimeError('app not found, options are : "ui", "protocol" and "auth"')

        try:
            r = app.router[route_name]
        except KeyError as e:
            route_names = ', '.join(sorted(app.router._named_resources))
            raise RuntimeError(f'route "{route_name}" not found, options are: {route_names}') from e
        assert None not in kwargs.values(), f'invalid kwargs, includes none: {kwargs}'
        url = r.url_for(**{k: str(v) for k, v in kwargs.items()})
        if query:
            url = url.with_query(**query)
        return url

    return f
