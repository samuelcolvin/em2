import email
import logging
import quopri
from datetime import datetime
from email.message import EmailMessage
from typing import List

from aiohttp.web_exceptions import HTTPBadRequest
from arq import ArqRedis
from bs4 import BeautifulSoup
from buildpg.asyncpg import BuildPgConnection

from em2.background import push_all, push_multiple
from em2.core import (
    ActionModel,
    ActionTypes,
    CreateConvModel,
    MsgFormat,
    UserTypes,
    apply_actions,
    create_conv,
    get_create_user,
)
from em2.settings import Settings

logger = logging.getLogger('em2.protocol.views.fallback')


async def remove_participants(conn: BuildPgConnection, conv_id: int, ts: datetime, user_ids: List[int]):
    """
    Remove participants from a conversation, doesn't use actions since apply_actions is not used, and actor changes.

    Should be called inside a transaction.
    """
    await conn.execute('delete from participants where conv=$1 and user_id=any($2)', conv_id, user_ids)

    # TODO add reason when removing participant
    r = await conn.fetch(
        """
        insert into actions (conv, ts, act, actor, participant_user)
          (select $1, $2, 'participant:remove', unnest($3::int[]), unnest($3::int[]))
        returning id
        """,
        conv_id,
        ts,
        user_ids,
    )
    await conn.execute('update participants set seen=false where conv=$1', conv_id)
    return [r_[0] for r_ in r]


class ProcessSMTP:
    __slots__ = 'conn', 'settings', 'redis'

    def __init__(self, conn, app):
        self.conn: BuildPgConnection = conn
        self.settings: Settings = app['settings']
        self.redis: ArqRedis = app['redis']

    async def run(self, msg: EmailMessage):
        # TODO deal with non multipart
        if msg['EM2-ID']:
            # this is an em2 message and should be received via the proper route too
            return

        _, actor_email = email.utils.parseaddr(msg['From'])
        assert actor_email, actor_email
        actor_email = actor_email.lower()

        message_id = msg.get('Message-ID', '').strip('<> ')
        recipients = await self.get_recipients(msg, message_id)
        timestamp = email.utils.parsedate_to_datetime(msg['Date'])

        conv_id, parent_msg_id = await self.get_conv(msg)
        actor_id = await get_create_user(self.conn, actor_email, UserTypes.remote_other)

        body, is_html = get_smtp_body(msg, message_id)
        async with self.conn.transaction():
            if conv_id:
                existing_prts = await self.conn.fetch(
                    'select email from participants p join users u on p.user_id = u.id where conv=$1', conv_id
                )
                existing_prts = {r[0] for r in existing_prts}
                new_prts = recipients - existing_prts
                actions = [ActionModel(act=ActionTypes.prt_add, participant=addr) for addr in new_prts]

                if body:
                    msg_format = MsgFormat.html if is_html else MsgFormat.plain
                    actions.append(
                        ActionModel(act=ActionTypes.msg_add, body=body, msg_format=msg_format, parent=parent_msg_id)
                    )

                conv_id, action_ids = await apply_actions(self.conn, self.settings, actor_id, conv_id, actions)
                assert action_ids

                await self.conn.execute(
                    'update actions set ts=$1 where conv=$2 and id=any($3)', timestamp, conv_id, action_ids
                )
                await self.conn.execute(
                    "insert into sends (action, ref, complete) values ($1, $2, true)", action_ids[0], message_id
                )
                await push_multiple(self.conn, self.redis, conv_id, action_ids, transmit=False)
            else:
                conv = CreateConvModel(
                    subject=msg['Subject'] or '-',
                    message=body,
                    msg_format=MsgFormat.html if is_html else MsgFormat.plain,
                    publish=True,
                    participants=[{'email': r} for r in recipients],
                )
                conv_id, conv_key = await create_conv(
                    conn=self.conn, creator_email=actor_email, creator_id=actor_id, conv=conv, ts=timestamp
                )
                await self.conn.execute(
                    """
                    insert into sends (action, ref, complete)
                    (select pk, $1, true from actions where conv=$2 order by id limit 1)
                    """,
                    message_id,
                    conv_id,
                )
                await push_all(self.conn, self.redis, conv_id, transmit=False)

    async def get_recipients(self, msg: EmailMessage, message_id: str):
        recipients = email.utils.getaddresses(msg.get_all('To', []) + msg.get_all('Cc', []))
        recipients = {a for n, a in recipients}
        if not recipients:
            logger.warning('email with no recipient, ignoring %s', message_id)
            raise HTTPBadRequest(text='no recipient, ignoring')

        loc_users = await self.conn.fetchval(
            "select 1 from users where user_type='local' and email=any($1) limit 1", recipients
        )
        if not loc_users:
            logger.warning('email with no local recipient (%r), ignoring %s', recipients, message_id)
            raise HTTPBadRequest(text='no local recipient, ignoring')
        return recipients

    async def get_conv(self, msg: EmailMessage):
        conv_id = parent_msg_id = None

        # find which conversation this relates to
        in_reply_to = msg['In-Reply-To']
        if in_reply_to:
            r = await self.conn.fetchrow(
                """
                select a.conv, a.id, a.act from sends
                join actions a on sends.action = a.id
                where sends.node is null and sends.ref = $1
                order by a.id desc
                limit 1
                """,
                in_reply_to.strip('<>\r\n'),
            )
            if r:
                conv_id, parent_id, msg_act = r
                if msg_act == ActionTypes.msg_add:
                    parent_msg_id = parent_id

        references = msg['References']
        if not conv_id and references:
            # try references instead to try and get conv_id
            ref_msg_ids = {msg_id.strip('<>\r\n') for msg_id in references.split(' ') if msg_id}
            if ref_msg_ids:
                conv_id = await self.conn.fetchval(
                    """
                    select a.conv from sends
                    join actions a on sends.action = a.id
                    where sends.node is null and sends.ref = any($1)
                    order by a.id desc
                    limit 1
                    """,
                    ref_msg_ids,
                )

        return conv_id, parent_msg_id


def get_email_body(msg: EmailMessage):
    body = None
    if msg.is_multipart():
        for m in msg.walk():
            ct = m['Content-Type']
            if 'text' in ct:
                body = m.get_payload()
                if 'text/html' in ct:
                    if m['Content-Transfer-Encoding'] == 'quoted-printable':
                        body = quopri.decodestring(body).decode()
                    return body, True
    else:
        body = msg.get_payload()
    return body, False


def get_smtp_body(msg: EmailMessage, message_id):
    # text/html is generally the best representation of the email
    body, is_html = get_email_body(msg)

    if not body:
        logger.warning('Unable to find body in email "%s"', message_id)

    if is_html:
        soup = BeautifulSoup(body, 'html.parser')

        # if this is a gmail email, remove the extra content
        gmail_extra = soup.select_one('div.gmail_extra') or soup.select_one('div.gmail_signature')
        if gmail_extra:
            gmail_extra.decompose()

        body = soup.prettify()
    return body.strip('\n'), is_html
