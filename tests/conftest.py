import asyncio
import base64
import json
import os
from dataclasses import dataclass
from email.message import EmailMessage
from io import BytesIO
from typing import List, Optional

import nacl.encoding
import nacl.signing
import pytest
from aiohttp import ClientSession, ClientTimeout
from aiohttp.test_utils import teardown_test_loop
from aioredis import create_redis
from arq import ArqRedis, Worker
from atoolbox.db.helpers import DummyPgPool
from atoolbox.test_utils import DummyServer, create_dummy_server
from buildpg import Values
from cryptography.fernet import Fernet
from PIL import Image, ImageDraw

from em2.auth.utils import mk_password
from em2.background import push_multiple
from em2.core import ActionModel, Connections, File, apply_actions
from em2.main import create_app
from em2.protocol.smtp import LogSmtpHandler, SesSmtpHandler
from em2.settings import Settings
from em2.utils.web import MakeUrl
from em2.worker import worker_settings

from . import dummy_server
from .resolver import TestDNSResolver


@pytest.fixture(scope='session', name='settings_session')
def _fix_settings_session():
    pg_db = 'em2_test'
    redis_db = 2

    test_worker = os.getenv('PYTEST_XDIST_WORKER')
    if test_worker:
        worker_id = int(test_worker.replace('gw', ''))
        redis_db = worker_id + 2
        if worker_id:
            pg_db = f'em2_test_{worker_id}'

    return Settings(
        testing=True,
        DATABASE_URL=f'postgres://postgres@localhost:5432/{pg_db}',
        REDISCLOUD_URL=f'redis://localhost:6379/{redis_db}',
        bcrypt_work_factor=6,
        max_request_size=1024 ** 2,
        aws_access_key='testing_access_key',
        aws_secret_key='testing_secret_key',
        ses_url_token='testing',
        aws_sns_signing_host='localhost',
        aws_sns_signing_schema='http',
        internal_auth_key='testing' * 6,
        auth_key=Fernet.generate_key(),
        s3_temp_bucket='s3_temp_bucket.example.com',
        s3_file_bucket='s3_files_bucket.example.com',
        s3_cache_bucket='s3_cache_bucket.example.com',
        max_ref_image_size=666,
        max_ref_image_count=10,
        vapid_private_key=(
            'MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgvGPhHfTSfxCod+wT'
            'zLuyK8KWjPGGvKJKJjzBGSF47YuhRANCAAQJNQfHBSOe5nI5fmUcwTFw3ckqXXvR'
            'F632vcMyB9RxPMaxicdqPiLg45GIk9oeEtm1kQjHQe7ikWxPFAm7uxkB'
        ),
        vapid_sub_email='vapid-reports@example.com',
    )


@pytest.fixture(scope='session', name='clean_db')
def _fix_clean_db(settings_session):
    # loop fixture has function scope so can't be used here.
    from atoolbox.db import prepare_database

    loop = asyncio.new_event_loop()
    loop.run_until_complete(prepare_database(settings_session, True))
    teardown_test_loop(loop)


@pytest.fixture(name='dummy_server')
async def _fix_dummy_server(loop, aiohttp_server):
    ctx = {'smtp': [], 's3_files': {}, 'webpush': []}
    return await create_dummy_server(aiohttp_server, extra_routes=dummy_server.routes, extra_context=ctx)


replaced_url_fields = 'grecaptcha_url', 'ses_endpoint_url', 's3_endpoint_url'


@pytest.fixture(name='settings')
def _fix_settings(dummy_server: DummyServer, tmpdir, settings_session):
    update = {f: f'{dummy_server.server_name}/{f}/' for f in replaced_url_fields}
    return settings_session.copy(update=update)


@pytest.fixture(name='db_conn')
async def _fix_db_conn(loop, settings, clean_db):
    from buildpg import asyncpg

    conn = await asyncpg.connect_b(dsn=settings.pg_dsn, loop=loop)

    tr = conn.transaction()
    await tr.start()

    yield conn

    await tr.rollback()
    await conn.close()


@pytest.fixture(name='conns')
def _fix_conns(db_conn, redis, settings):
    return Connections(db_conn, redis, settings)


@pytest.yield_fixture
async def redis(loop, settings):
    addr = settings.redis_settings.host, settings.redis_settings.port

    redis = await create_redis(addr, db=settings.redis_settings.database, encoding='utf8', commands_factory=ArqRedis)
    await redis.flushdb()

    yield redis

    redis.close()
    await redis.wait_closed()


async def pre_startup_app(app):
    app['pg'] = DummyPgPool(app['test_conn'])


@pytest.fixture(name='cli')
async def _fix_cli(settings, db_conn, aiohttp_client, redis, loop):
    app = await create_app(settings=settings)
    app['test_conn'] = db_conn
    app.on_startup.insert(0, pre_startup_app)
    cli = await aiohttp_client(app)
    settings.local_port = cli.server.port

    async def post_json(url, data=None, *, origin=None, status=200):
        if isinstance(data, (dict, list)):
            data = json.dumps(data)

        r = await cli.post(
            url,
            data=data or '{}',
            headers={
                'Content-Type': 'application/json',
                'Referer': 'http://localhost:3000/dummy-referer/',
                'Origin': origin or 'http://localhost:3000',
            },
        )
        if status:
            assert r.status == status, await r.text()
        return r

    async def get_json(url, *, status=200, **kwargs):
        r = await cli.get(url, **kwargs)
        assert r.status == status, await r.text()
        return await r.json()

    cli.post_json = post_json
    cli.get_json = get_json
    return cli


@pytest.fixture(name='url')
def _fix_url(cli):
    return MakeUrl(cli.server.app).get_path


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
    def __init__(self, redis, cli, url):
        self.redis: ArqRedis = redis
        self.cli = cli
        self.conn = self.cli.server.app['pg']
        self.conns = Connections(self.conn, self.redis, cli.server.app['settings'])
        self.email_index = 1

        self.user: User = None
        self.conv: Conv = None
        self._url = url

    async def create_user(self, *, login=True, email=None, first_name='Tes', last_name='Ting', pw='testing') -> User:
        if email is None:
            email = f'testing-{self.email_index}@example.com'
            self.email_index += 1

        password_hash = mk_password(pw, self.conns.settings)
        auth_user_id = await self.conn.fetchval(
            """
            insert into auth_users (email, first_name, last_name, password_hash, account_status)
            values ($1, $2, $3, $4, 'active')
            on conflict (email) do nothing returning id
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

    async def create_conv(
        self, subject='Test Subject', message='Test Message', session_id=None, participants=(), publish=False
    ) -> Conv:
        data = {'subject': subject, 'message': message, 'publish': publish, 'participants': participants}
        r = await self.cli.post_json(
            self.url('ui:create', session_id=session_id or self.user.session_id), data, status=201
        )
        conv_key = (await r.json())['key']
        conv_id = await self.conn.fetchval('select id from conversations where key=$1', conv_key)
        conv = Conv(conv_key, conv_id)
        self.conv = self.conv or conv
        return conv

    async def create_label(self, name='Test Label', *, user_id=None, ordering=None, color=None, description=None):
        val = dict(name=name, user_id=user_id or self.user.id, ordering=ordering, color=color, description=description)
        values = Values(**{k: v for k, v in val.items() if v is not None})
        return await self.conn.fetchval_b(
            'insert into labels (:values__names) values :values returning id', values=values
        )

    async def act(
        self, actor_user_id: int, conv_id: int, action: ActionModel, files: Optional[List[File]] = None
    ) -> List[int]:
        conv_id, action_ids = await apply_actions(self.conns, actor_user_id, conv_id, [action], files=files)

        if action_ids:
            await push_multiple(self.conns, conv_id, action_ids)
        return action_ids


@pytest.fixture
async def factory(redis, cli, url):
    return Factory(redis, cli, url)


@pytest.yield_fixture(name='worker_ctx')
async def _fix_worker_ctx(redis, settings, db_conn, dummy_server):
    session = ClientSession(timeout=ClientTimeout(total=10))
    ctx = dict(
        settings=settings,
        pg=DummyPgPool(db_conn),
        client_session=session,
        resolver=TestDNSResolver(dummy_server),
        redis=redis,
        signing_key=nacl.signing.SigningKey(seed=settings.signing_secret_key, encoder=nacl.encoding.HexEncoder),
    )
    ctx.update(smtp_handler=LogSmtpHandler(ctx), conns=Connections(ctx['pg'], redis, settings))

    yield ctx

    await session.close()


@pytest.yield_fixture(name='worker')
async def _fix_worker(redis, worker_ctx):
    worker = Worker(
        functions=worker_settings['functions'], redis_pool=redis, burst=True, poll_delay=0.01, ctx=worker_ctx
    )

    yield worker

    worker.pool = None
    await worker.close()


@pytest.yield_fixture(name='ses_worker')
async def _fix_ses_worker(redis, settings, db_conn, dummy_server):
    session = ClientSession(timeout=ClientTimeout(total=10))
    ctx = dict(
        settings=settings,
        pg=DummyPgPool(db_conn),
        client_session=session,
        resolver=TestDNSResolver(dummy_server),
        signing_key=nacl.signing.SigningKey(seed=settings.signing_secret_key, encoder=nacl.encoding.HexEncoder),
    )
    ctx.update(smtp_handler=SesSmtpHandler(ctx), conns=Connections(ctx['pg'], redis, settings))
    worker = Worker(functions=worker_settings['functions'], redis_pool=redis, burst=True, poll_delay=0.01, ctx=ctx)

    yield worker

    await ctx['smtp_handler'].shutdown()
    worker.pool = None
    await worker.close()
    await session.close()


@pytest.fixture(name='send_to_remote')
async def _fix_send_to_remote(factory: Factory, worker: Worker, db_conn):
    await factory.create_user()
    await factory.create_conv(participants=[{'email': 'sender@example.net'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await worker.async_run()
    assert (worker.jobs_complete, worker.jobs_failed, worker.jobs_retried) == (3, 0, 0)
    assert 1 == await db_conn.fetchval('select count(*) from sends')
    return await db_conn.fetchrow('select id, ref from sends')


@pytest.fixture(name='sns_data')
def _fix_sns_data(dummy_server: DummyServer, mocker):
    def run(message_id, *, mock_verify=True, **message):
        if mock_verify:
            mocker.patch('em2.protocol.views.smtp_ses.x509.load_pem_x509_certificate')
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


@pytest.fixture(name='attachment')
def _fix_attachment():
    def run(filename, mime_type, content, headers=None):
        attachment = EmailMessage()
        for k, v in (headers or {}).items():
            attachment[k] = v
        maintype, subtype = mime_type.split('/', 1)
        kwargs = dict(subtype=subtype, filename=filename)
        if maintype != 'text':
            # not sure why this is
            kwargs['maintype'] = maintype
        attachment.set_content(content, **kwargs)
        for k, v in (headers or {}).items():
            if k in attachment:
                attachment.replace_header(k, v)
            else:
                attachment.add_header(k, v)
        return attachment

    return run


@pytest.fixture(name='create_email')
def _fix_create_email():
    def run(
        subject='Test Subject',
        e_from='sender@example.net',
        to=('testing-1@example.com',),
        text_body='this is a message.',
        html_body='this is an html <b>message</b>.',
        message_id='message-id@example.net',
        attachments=(),
        headers=None,
    ):
        email_msg = EmailMessage()
        if message_id is not None:
            email_msg['Message-ID'] = message_id
        email_msg['Subject'] = subject
        email_msg['From'] = e_from
        email_msg['To'] = ','.join(to)
        # email.utils.format_datetime(datetime(2032, 1, 1, 12, 0))
        email_msg['Date'] = 'Thu, 01 Jan 2032 12:00:00 -0000'

        for k, v in (headers or {}).items():
            email_msg[k] = v

        text_body and email_msg.set_content(text_body)
        html_body and email_msg.add_alternative(html_body, subtype='html')

        for attachment in attachments:
            if email_msg.get_content_type() != 'multipart/mixed':
                email_msg.make_mixed()
            email_msg.attach(attachment)

        return email_msg

    return run


@pytest.fixture(name='create_ses_email')
def _fix_create_ses_email(dummy_server, sns_data, create_email):
    def run(
        *args,
        to=('testing-1@example.com',),
        key='foobar',
        headers=None,
        message_id='message-id@example.net',
        receipt_extra=None,
        **kwargs,
    ):
        msg = create_email(*args, to=to, message_id=message_id, headers=headers, **kwargs)
        dummy_server.app['s3_files'][key] = msg.as_string()

        headers = headers or {}
        h = [{'name': k, 'value': v} for k, v in headers.items()]
        if message_id is not None:
            h.append({'name': 'Message-ID', 'value': message_id})
        mail = dict(headers=h, commonHeaders={'to': list(to)})
        receipt = dict(
            action={'type': 'S3', 'bucketName': 'em2-testing', 'objectKeyPrefix': '', 'objectKey': key},
            spamVerdict={'status': 'PASS'},
            virusVerdict={'status': 'PASS'},
            spfVerdict={'status': 'PASS'},
            dkimVerdict={'status': 'PASS'},
            dmarcVerdict={'status': 'PASS'},
        )
        receipt.update(receipt_extra or {})
        return sns_data(message_id, notificationType='Received', mail=mail, receipt=receipt)

    return run


@pytest.fixture(name='create_image')
def _fix_create_image():
    def create_image(image_format='JPEG'):
        stream = BytesIO()

        image = Image.new('RGB', (400, 300), (50, 100, 150))
        ImageDraw.Draw(image).polygon([(0, 0), (image.width, 0), (image.width, 100), (0, 100)], fill=(128, 128, 128))
        image.save(stream, format=image_format, optimize=True)
        return stream.getvalue()

    return create_image


@pytest.fixture(name='web_push_sub')
def _fix_web_push_sub(dummy_server):
    return {
        'endpoint': dummy_server.server_name.replace('localhost', '127.0.0.1') + '/vapid/',
        'expirationTime': None,
        'keys': {
            # generated by code in dummy_server.py
            'p256dh': 'BGsX0fLhLEJH-Lzm5WOkQPJ3A32BLeszoPShOUXYmMKWT-NC4v4af5uO5-tKfA-eFivOM1drMV7Oy7ZAaDe_UfU',
            'auth': 'x' * 32,
        },
    }
