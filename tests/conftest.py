import asyncio
import json
from dataclasses import dataclass

import pytest
from aiohttp.test_utils import teardown_test_loop
from atoolbox.test_utils import DummyServer, create_dummy_server

from em2.auth.utils import mk_password
from em2.main import create_app
from em2.settings import Settings


def pytest_addoption(parser):
    parser.addoption('--reuse-db', action='store_true', default=False, help='keep the existing database if it exists')


settings_args = dict(
    DATABASE_URL='postgres://postgres@localhost:5432/em2_test',
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
                'Referer': 'http://localhost:3000/dummy-referer/',
                'Origin': origin or 'http://localhost:3000',
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


@dataclass
class User:
    email: str
    first_name: str
    last_name: str
    password: str
    auth_user_id: int
    id: int = None


@dataclass
class Conv:
    key: str
    id: int


class Factory:
    def __init__(self, conn, cli, url):
        self.conn = conn
        self.cli = cli
        self.url = url
        self.settings: Settings = cli.server.app['settings']
        self.email_index = 1

        self.user: User = None
        self.conv: Conv = None

    async def create_user(self, *, login=True, email=None, first_name='Tes', last_name='Ting', pw='testing') -> User:
        if email is None:
            email = f'testing-{self.email_index}@example.com'
            self.email_index += 1

        password_hash = mk_password(pw, self.settings)
        auth_user_id = await self.conn.fetchval(
            """
            INSERT INTO auth_users (email, first_name, last_name, password_hash, account_status)
            VALUES ($1, $2, $3, $4, 'active')
            ON CONFLICT (email) DO NOTHING RETURNING id
            """,
            email,
            first_name,
            last_name,
            password_hash,
        )
        if not auth_user_id:
            raise RuntimeError(f'user with email {email} already exists')

        user_id = None
        if login:
            await self.login(email, pw)
            user_id = await self.conn.fetchval('select id from users where email=$1', email)

        user = User(email, first_name, last_name, pw, auth_user_id, user_id)
        self.user = self.user or user
        return user

    async def login(self, email, password, *, captcha=False):
        data = dict(email=email, password=password)
        if captcha:
            data['grecaptcha_token'] = '__ok__'

        r = await self.cli.post(
            self.url('auth:login'),
            data=json.dumps(data),
            headers={'Content-Type': 'application/json', 'Origin': 'null'},
        )
        assert r.status == 200, await r.text()
        obj = await r.json()

        r = await self.cli.post_json(self.url('ui:auth-token'), data={'auth_token': obj['auth_token']})
        assert r.status == 200, await r.text()
        assert len(self.cli.session.cookie_jar) == 1
        return r

    async def create_conv(self, subject='Test Subject', message='Test Message', publish=False) -> Conv:
        data = {'subject': subject, 'message': message, 'publish': publish}
        r = await self.cli.post_json(self.url('ui:create'), data)
        assert r.status == 201, await r.text()
        conv_key = (await r.json())['key']
        conv_id = await self.conn.fetchval('select id from conversations where key=$1', conv_key)
        conv = Conv(conv_key, conv_id)
        self.conv = self.conv or conv
        return conv


@pytest.fixture
async def factory(db_conn, cli, url):
    return Factory(db_conn, cli, url)
