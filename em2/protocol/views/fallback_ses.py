import asyncio
import base64
import json
import logging
from secrets import compare_digest
from typing import Dict

from aiohttp.web_exceptions import HTTPUnauthorized
from aiohttp.web_response import Response
from buildpg import Values
from pydantic.datetime_parse import parse_datetime

from em2.background import push_multiple

from .fallback_utils import ProcessSMTP, remove_participants

logger = logging.getLogger('em2.protocol.ses')


async def process_email(request, message: Dict):
    # TODO check X-SES-Spam-Verdict, X-SES-Virus-Verdict from message['headers']
    process_smtp = ProcessSMTP(request['conn'], request.app)
    smtp_content = base64.b64decode(message['content']).decode()
    await process_smtp.run(smtp_content)


async def record_email_event(request, message: Dict):
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


async def ses_webhook(request):
    pw = request.app['settings'].ses_webhook_auth
    expected_auth_header = f'Basic {base64.b64encode(pw).decode()}'
    actual_auth_header = request.headers.get('Authorization', '')
    if not compare_digest(expected_auth_header, actual_auth_header):
        raise HTTPUnauthorized(text='Invalid basic auth', headers={'WWW-Authenticate': 'Basic'})

    # content type is plain text for SNS, so we have to decode json manually
    data = json.loads(await request.text())
    sns_type = data['Type']
    if sns_type == 'SubscriptionConfirmation':
        logger.info('confirming aws Subscription')
        # TODO check we actually want this subscription
        async with request.app['http_client'].head(data['SubscribeURL']) as r:
            assert r.status == 200, r.status
    else:
        assert sns_type == 'Notification', sns_type
        message = json.loads(data.get('Message'))
        # is this right?
        if message.get('notificationType') == 'Received':
            await asyncio.shield(process_email(request, message))
        else:
            await asyncio.shield(record_email_event(request, message))
    return Response(status=204)
