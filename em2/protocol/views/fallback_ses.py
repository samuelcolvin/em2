import asyncio
import base64
import email
import hashlib
import json
import logging
from secrets import compare_digest
from typing import Dict

import aiobotocore
from aiohttp.web_response import Response
from atoolbox import JsonErrors
from buildpg import Values
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic.datetime_parse import parse_datetime
from yarl import URL

from em2.background import push_multiple
from em2.settings import Settings

from .fallback_utils import ProcessSMTP, get_email_recipients, remove_participants

logger = logging.getLogger('em2.protocol.ses')


async def ses_webhook(request):
    if not compare_digest(request.app['settings'].ses_url_token, request.match_info['token']):
        raise JsonErrors.HTTPForbidden('invalid url')

    # content type is plain text for SNS, so we have to decode json manually
    try:
        data = json.loads(await request.text())
    except ValueError:
        raise JsonErrors.HTTPBadRequest('invalid json')
    await verify_sns(request, data)

    # avoid keeping multiple copies of the request data in memory
    request._read_byte = None
    sns_type = data['Type']
    if sns_type == 'SubscriptionConfirmation':
        logger.info('confirming aws Subscription')
        # TODO check we actually want this subscription
        async with request.app['http_client'].head(data['SubscribeURL']) as r:
            assert r.status == 200, r.status
    else:
        assert sns_type == 'Notification', sns_type
        message = json.loads(data['Message'])
        del data
        if message.get('notificationType') == 'Received':
            await asyncio.shield(_record_email_message(request, message))
        else:
            await asyncio.shield(_record_email_event(request, message))
    return Response(status=204)


async def _record_email_message(request, message: Dict):
    """
    Record the email, check email should be processed before starting the job.
    """
    # TODO check X-SES-Spam-Verdict, X-SES-Virus-Verdict from message['receipt']
    headers = {h['name']: h['value'] for h in message['headers']}
    if headers.get('EM2-ID'):
        # this is an em2 message and should be received via the proper route too
        return

    message_id = headers['Message-ID'].strip('<> ')
    to, cc = message['commonHeaders'].get('to', []), message['commonHeaders'].get('cc', [])
    # make sure we don't process unnecessary messages, could also delete from S3
    await get_email_recipients(to, cc, message_id, request['conn'])

    s3_action = message['receipt']['action']
    bucket, prefix, path = s3_action['bucketName'], s3_action['objectKeyPrefix'], s3_action['objectKey']
    if prefix:
        path = f'{prefix}/{path}'
    await request.app['redis'].enqueue_job('record_ses_email', bucket, path, _defer_by=-5)


async def record_ses_email(ctx, bucket, path):
    async with create_s3_session(ctx['settings']) as s3:
        r = await s3.get_object(Bucket=bucket, Key=path)
        async with r['Body'] as stream:
            body = await stream.read()

    msg = email.message_from_string(body.decode())
    del body, r
    async with ctx['pg'].acquire() as conn:
        await ProcessSMTP(ctx, conn).run(msg)


async def _record_email_event(request, message: Dict):
    """
    record SES SMTP events, this could be run on the worker.
    """
    conn = request['conn']
    msg_id = message['mail']['messageId']
    r = await conn.fetchrow(
        """
        select s.id, s.complete, a.conv from sends s
        join actions a on s.action = a.pk
        where s.node is null and s.ref=$1
        """,
        msg_id,
    )
    if not r:
        return
    send_id, send_complete, conv_id = r

    event_type = message.get('eventType')
    extra = {}
    data = message.get(event_type.lower()) or {}
    user_ids = []
    complaint = False

    if event_type == 'Send':
        data = message['mail']
    elif event_type == 'Delivery':
        extra['processingTimeMillis'] = data.get('processingTimeMillis')
    elif event_type == 'Open':
        # can't use this to mark seen=True since we don't know who opened the email
        extra.update(ipAddress=data.get('ipAddress'), userAgent=data.get('userAgent'))
    elif event_type == 'Bounce':
        user_ids = await conn.fetchval(
            """
            select array_agg(id) from (
              select u.id from participants p
              join users u on p.user_id = u.id
              where u.email = any($1) and p.conv = $2
            ) as t
            """,
            [v['emailAddress'] for v in data.get('bouncedRecipients', [])],
            conv_id,
        )
        extra.update(
            bounceType=data.get('bounceType'),
            bounceSubType=data.get('bounceSubType'),
            bouncedRecipients=data.get('bouncedRecipients'),
            reportingMTA=data.get('reportingMTA'),
            remoteMtaIp=data.get('remoteMtaIp'),
            feedbackId=data.get('feedbackId'),
        )
    elif event_type == 'Complaint':
        # TODO perhaps need to deal with complaintFeedbackType=not-spam specially
        # see https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html
        emails = [v['emailAddress'] for v in data.get('complainedRecipients', [])]
        complaint = True
        user_ids = await conn.fetchval(
            """
            select array_agg(id) from (
              select u.id from participants p
              join users u on p.user_id = u.id
              where u.email = any($1) and p.conv = $2
            ) as t
            """,
            emails,
            conv_id,
        )
        extra.update(
            complaintFeedbackType=data.get('complaintFeedbackType'),
            feedbackId=data.get('feedbackId'),
            userAgent=data.get('userAgent'),
            emails=emails,
        )
    else:
        logger.warning('unknown aws webhooks %s', event_type, extra={'data': {'message': message}})

    ts = parse_datetime(data['timestamp'])
    values = dict(send=send_id, status=event_type, user_ids=user_ids or None, ts=ts)
    extra = {k: v for k, v in extra.items() if v}
    if extra:
        values['extra'] = json.dumps(extra)

    async with conn.transaction():
        await conn.execute_b('insert into send_events (:values__names) values :values', values=Values(**values))
        if not send_complete:
            await conn.execute('update sends set complete=true where id=$1', send_id)

        if complaint:
            action_ids = await remove_participants(conn, conv_id, ts, user_ids)
            await push_multiple(conn, request.app['redis'], conv_id, action_ids)

    return event_type


async def verify_sns(request, data: Dict):
    if data.get('Type') == 'Notification':
        fields = 'Message', 'MessageId', 'Subject', 'Timestamp', 'TopicArn', 'Type'
    else:
        fields = 'Message', 'MessageId', 'SubscribeURL', 'Timestamp', 'Token', 'TopicArn', 'Type'

    try:
        canonical_msg = ''.join(f'{f}\n{data[f]}\n' for f in fields).encode()
        sign_url = data['SigningCertURL']
        signature = base64.b64decode(data['Signature'])
    except (KeyError, ValueError) as e:
        raise JsonErrors.HTTPForbidden(f'invalid request, error: {e}')

    cache_key = 'sns-signing-url:' + hashlib.md5(sign_url.encode()).hexdigest()
    sign_url = URL(sign_url)
    settings: Settings = request.app['settings']
    if sign_url.scheme != settings.aws_sns_signing_schema or not sign_url.host.endswith(settings.aws_sns_signing_host):
        logger.warning('invalid signing url "%s"', sign_url)
        raise JsonErrors.HTTPForbidden('invalid signing cert url')

    pem_data = await request.app['redis'].get(cache_key, encoding=None)
    if not pem_data:
        async with request.app['http_client'].get(sign_url, raise_for_status=True) as r:
            pem_data = await r.read()
        await request.app['redis'].setex(cache_key, 86400, pem_data)

    cert = x509.load_pem_x509_certificate(pem_data, default_backend())
    pubkey: rsa.RSAPublicKey = cert.public_key()
    try:
        pubkey.verify(signature, canonical_msg, padding.PKCS1v15(), cert.signature_hash_algorithm)
    except InvalidSignature:
        raise JsonErrors.HTTPForbidden('invalid signature')


def create_s3_session(settings: Settings):
    session = aiobotocore.get_session()
    return session.create_client(
        's3',
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key,
        aws_secret_access_key=settings.aws_secret_key,
        endpoint_url=settings.s3_endpoint_url,
    )
