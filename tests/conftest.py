import asyncio
import base64
import email
import json
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import List

import aiodns
import pytest
from aiohttp import ClientSession, ClientTimeout
from aiohttp.test_utils import teardown_test_loop
from aioredis import create_redis
from arq import ArqRedis, Worker
from atoolbox.db.helpers import SimplePgPool
from atoolbox.test_utils import DummyServer, create_dummy_server

from em2.auth.utils import mk_password
from em2.background import push_multiple
from em2.core import ActionModel, apply_actions
from em2.main import create_app
from em2.protocol.fallback import LogFallbackHandler, SesFallbackHandler
from em2.protocol.worker import worker_settings
from em2.settings import Settings
from em2.utils.web import MakeUrl

from . import dummy_server


def pytest_addoption(parser):
    parser.addoption('--reuse-db', action='store_true', default=False, help='keep the existing database if it exists')


settings_args = dict(
    DATABASE_URL='postgres://postgres@localhost:5432/em2_test',
    REDISCLOUD_URL='redis://localhost:6379/6',
    bcrypt_work_factor=6,
    max_request_size=1024 ** 2,
    aws_access_key='testing_access_key',
    aws_secret_key='testing_secret_key',
    ses_url_token='testing',
    aws_sns_signing_host='localhost',
    aws_sns_signing_schema='http',
    internal_auth_key='testing' * 6,
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
    ctx = {'smtp': [], 's3_emails': {}}
    return await create_dummy_server(aiohttp_server, extra_routes=dummy_server.routes, extra_context=ctx)


replaced_url_fields = 'grecaptcha_url', 'ses_endpoint_url', 's3_endpoint_url'


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

    redis = await create_redis(addr, db=settings.redis_settings.database, encoding='utf8', commands_factory=ArqRedis)
    await redis.flushdb()

    yield redis

    redis.close()
    await redis.wait_closed()


async def pre_startup_app(app):
    app['pg'] = SimplePgPool(app['test_conn'])


@pytest.fixture(name='cli')
async def _fix_cli(settings, db_conn, aiohttp_client, redis, loop):
    app = await create_app(settings=settings)
    app['test_conn'] = db_conn
    app.on_startup.insert(0, pre_startup_app)
    cli = await aiohttp_client(app)
    settings.local_port = cli.server.port

    async def post_json(url, data=None, *, origin=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data)

        return await cli.post(
            url,
            data=data or '{}',
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
    return MakeUrl(cli.server.app)


@dataclass
class User:
    email: str
    first_name: str
    last_name: str
    password: str
    auth_user_id: int
    id: int = None
    session_id: int = None


@dataclass
class Conv:
    key: str
    id: int


class Factory:
    def __init__(self, conn, redis, cli, url):
        self.conn = conn
        self.redis: ArqRedis = redis
        self.cli = cli
        self.settings: Settings = cli.server.app['settings']
        self.email_index = 1

        self.user: User = None
        self.conv: Conv = None
        self._url = url

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
        session_id = None
        if login:
            r1, r2 = await self.login(email, pw)
            obj = await r1.json()
            session_id = obj['session']['session_id']
            user_id = await self.conn.fetchval('select id from users where email=$1', email)

        user = User(email, first_name, last_name, pw, auth_user_id, user_id, session_id)
        self.user = self.user or user
        return user

    def url(self, name, *, query=None, **kwargs):
        if self.user and name.startswith('ui:'):
            kwargs.setdefault('session_id', self.user.session_id)
        return self._url(name, query=query, **kwargs)

    async def login(self, email, password, *, captcha=False):
        data = dict(email=email, password=password)
        if captcha:
            data['grecaptcha_token'] = '__ok__'

        r1 = await self.cli.post(
            self._url('auth:login'),
            data=json.dumps(data),
            headers={'Content-Type': 'application/json', 'Origin': 'null'},
        )
        assert r1.status == 200, await r1.text()
        obj = await r1.json()

        r2 = await self.cli.post_json(self._url('ui:auth-token'), data={'auth_token': obj['auth_token']})
        assert r2.status == 200, await r2.text()
        assert len(self.cli.session.cookie_jar) == 1
        return r1, r2

    async def create_conv(self, subject='Test Subject', message='Test Message', participants=[], publish=False) -> Conv:
        data = {'subject': subject, 'message': message, 'publish': publish, 'participants': participants}
        r = await self.cli.post_json(self.url('ui:create'), data)
        assert r.status == 201, await r.text()
        conv_key = (await r.json())['key']
        conv_id = await self.conn.fetchval('select id from conversations where key=$1', conv_key)
        conv = Conv(conv_key, conv_id)
        self.conv = self.conv or conv
        return conv

    async def act(self, actor_user_id: int, conv_id: int, action: ActionModel) -> List[int]:
        conv_id, action_ids = await apply_actions(self.conn, self.settings, actor_user_id, conv_id, [action])

        if action_ids:
            await push_multiple(self.conn, self.redis, conv_id, action_ids)
        return action_ids


@pytest.fixture
async def factory(db_conn, redis, cli, url):
    return Factory(db_conn, redis, cli, url)


@pytest.yield_fixture(name='worker')
async def _fix_worker(redis, settings, db_conn):
    session = ClientSession(timeout=ClientTimeout(total=10))
    ctx = dict(
        settings=settings,
        pg=SimplePgPool(db_conn),
        session=session,
        resolver=aiodns.DNSResolver(nameservers=['1.1.1.1', '1.0.0.1']),
    )
    ctx['fallback_handler'] = LogFallbackHandler(ctx)
    worker = Worker(functions=worker_settings['functions'], redis_pool=redis, burst=True, poll_delay=0.01, ctx=ctx)

    yield worker

    worker.pool = None
    await worker.close()
    await session.close()


@pytest.yield_fixture(name='ses_worker')
async def _fix_ses_worker(redis, settings, db_conn):
    session = ClientSession(timeout=ClientTimeout(total=10))
    ctx = dict(
        settings=settings,
        pg=SimplePgPool(db_conn),
        session=session,
        resolver=aiodns.DNSResolver(nameservers=['1.1.1.1', '1.0.0.1']),
    )
    ctx['fallback_handler'] = SesFallbackHandler(ctx)
    worker = Worker(functions=worker_settings['functions'], redis_pool=redis, burst=True, poll_delay=0.01, ctx=ctx)

    yield worker

    await ctx['fallback_handler'].shutdown()
    worker.pool = None
    await worker.close()
    await session.close()


@pytest.fixture(name='send_to_remote')
async def _fix_send_to_remote(factory: Factory, worker: Worker, db_conn):
    await factory.create_user()
    await factory.create_conv(participants=[{'email': 'whomever@remote.com'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await worker.async_run()
    assert (worker.jobs_complete, worker.jobs_failed, worker.jobs_retried) == (2, 0, 0)
    assert 1 == await db_conn.fetchval('select count(*) from sends')
    return await db_conn.fetchrow('select id, ref from sends')


@pytest.fixture(name='sns_data')
def _fix_sns_data(dummy_server, mocker):
    def run(message_id, *, mock_verify=True, **message):
        if mock_verify:
            mocker.patch('em2.protocol.views.fallback_ses.x509.load_pem_x509_certificate')
        return {
            'Type': 'Notification',
            'MessageId': message_id,
            'Subject': 'Amazon SES Email Receipt Notification',
            'Timestamp': '2032-03-11T18:00:00.000Z',
            'TopicArn': 'arn:aws:sns:us-east-1:123:em2-webhook',
            'Message': json.dumps(message),
            'SigningCertURL': dummy_server.server_name + '/sns_signing_url.pem',
            'Signature': base64.b64encode(b'the signature').decode(),
        }

    return run


@pytest.fixture(name='create_email')
def _fix_create_email(dummy_server, sns_data):
    def run(
        subject='Test Subject',
        e_from='whomever@remote.com',
        to=('testing-1@example.com',),
        text_body='this is a message.',
        html_body='this is an html <b>message</b>.',
        message_id='message-id@remote.com',
        key='foobar',
        **headers,
    ):
        email_msg = EmailMessage()
        email_msg['Message-ID'] = message_id
        email_msg['Subject'] = subject
        email_msg['From'] = e_from
        email_msg['To'] = ','.join(to)
        email_msg['Date'] = email.utils.format_datetime(datetime(2032, 1, 1, 12, 0))

        for k, v in headers.items():
            email_msg[k] = v

        text_body and email_msg.set_content(text_body)
        html_body and email_msg.add_alternative(html_body, subtype='html')
        dummy_server.app['s3_emails'][key] = email_msg.as_string()

        h = [{'name': 'Message-ID', 'value': message_id}] + [{'name': k, 'value': v} for k, v in headers.items()]
        return sns_data(
            message_id,
            notificationType='Received',
            mail=dict(headers=h, commonHeaders={'to': list(to)}),
            receipt={'action': {'type': 'S3', 'bucketName': 'em2-testing', 'objectKeyPrefix': '', 'objectKey': key}},
        )

    return run
