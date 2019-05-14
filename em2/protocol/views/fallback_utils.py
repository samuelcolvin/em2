import email
import logging
import quopri
import re
from datetime import datetime
from email.message import EmailMessage
from typing import List, Set, Tuple

from aiohttp.abc import Request
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
from em2.utils.smtp import find_smtp_files

logger = logging.getLogger('em2.protocol.views.fallback')

__all__ = ['remove_participants', 'get_email_recipients', 'process_smtp']


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


async def get_email_recipients(to: List[str], cc: List[str], message_id: str, conn: BuildPgConnection) -> Set[str]:
    recipients = email.utils.getaddresses(to + cc)
    recipients = {a for n, a in recipients}
    if not recipients:
        logger.warning('email with no recipient, ignoring %s', message_id)
        raise HTTPBadRequest(text='no recipient, ignoring')

    loc_users = await conn.fetchval("select 1 from users where user_type='local' and email=any($1) limit 1", recipients)
    if not loc_users:
        logger.warning('email with no local recipient (%r), ignoring %s', recipients, message_id)
        raise HTTPBadRequest(text='no local recipient, ignoring')
    return recipients


async def process_smtp(
    request: Request, msg: EmailMessage, recipients: Set[str], storage: str, *, spam: bool = None, warnings: dict = None
):
    assert not msg['EM2-ID'], 'messages with EM2-ID header should be filtered out before this'
    p = ProcessSMTP(request)
    await p.run(msg, recipients, storage, spam, warnings)


inline_regex = re.compile(' src')


class ProcessSMTP:
    __slots__ = 'conn', 'settings', 'redis'

    def __init__(self, request):
        self.conn: BuildPgConnection = request['conn']
        self.redis: ArqRedis = request.app['redis']
        self.settings: Settings = request.app['settings']

    async def run(self, msg: EmailMessage, recipients: Set[str], storage: str, spam: bool, warnings: dict):
        # TODO deal with non multipart
        _, actor_email = email.utils.parseaddr(msg['From'])
        assert actor_email, actor_email
        actor_email = actor_email.lower()

        message_id = msg.get('Message-ID', '').strip('<> ')
        timestamp = email.utils.parsedate_to_datetime(msg['Date'])

        conv_id, original_actor_id = await self.get_conv(msg)
        actor_id = await get_create_user(self.conn, actor_email, UserTypes.remote_other)

        existing_conv = bool(conv_id)
        body, is_html = get_smtp_body(msg, message_id, existing_conv)
        async with self.conn.transaction():
            if existing_conv:
                existing_prts = await self.conn.fetch(
                    'select email from participants p join users u on p.user_id=u.id where conv=$1', conv_id
                )
                existing_prts = {r[0] for r in existing_prts}
                if actor_email not in existing_prts:
                    # reply from different address, we need to add the new address to the conversation
                    a = ActionModel(act=ActionTypes.prt_add, participant=actor_email)
                    _, all_action_ids = await apply_actions(
                        self.conn, self.redis, self.settings, original_actor_id, conv_id, [a]
                    )
                    assert all_action_ids
                else:
                    all_action_ids = []

                new_prts = recipients - existing_prts

                msg_format = MsgFormat.html if is_html else MsgFormat.plain
                actions = [ActionModel(act=ActionTypes.msg_add, body=body or '', msg_format=msg_format)]

                actions += [ActionModel(act=ActionTypes.prt_add, participant=addr) for addr in new_prts]

                _, action_ids = await apply_actions(
                    self.conn, self.redis, self.settings, actor_id, conv_id, actions, spam, warnings
                )
                assert action_ids

                all_action_ids += action_ids
                await self.conn.execute(
                    'update actions set ts=$1 where conv=$2 and id=any($3)', timestamp, conv_id, all_action_ids
                )
                send_id = await self.conn.fetchval(
                    """
                    insert into sends (action, ref, complete, storage)
                    (select pk, $1, true, $2 from actions where conv=$3 and id=any($4) and act='message:add')
                    returning id
                    """,
                    message_id,
                    storage,
                    conv_id,
                    action_ids,
                )
                await self.store_attachments(send_id, msg)
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
                    conn=self.conn,
                    redis=self.redis,
                    creator_email=actor_email,
                    creator_id=actor_id,
                    conv=conv,
                    ts=timestamp,
                    spam=spam,
                    warnings=warnings,
                )
                send_id = await self.conn.fetchval(
                    """
                    insert into sends (action, ref, complete, storage)
                    (select pk, $1, true, $2 from actions where conv=$3 and act='message:add')
                    returning id
                    """,
                    message_id,
                    storage,
                    conv_id,
                )
                await self.store_attachments(send_id, msg)
                await push_all(self.conn, self.redis, conv_id, transmit=False)

    async def store_attachments(self, send_id: int, msg: EmailMessage):
        files = list(find_smtp_files(msg))
        if files:
            action_pk, conv_id = await self.conn.fetchrow(
                """
                select s.action, a.conv
                from sends s
                join actions a on s.action = a.pk
                where s.id=$1
                """,
                send_id,
            )
            files = [
                (conv_id, action_pk, send_id, f.content_disp, f.hash, f.content_id, f.name, f.content_type)
                for f in files
            ]
            await self.conn.executemany(
                """
                insert into files (conv  , action, send, content_disp, hash, content_id, name, content_type)
                values            ($1    , $2    , $3  , $4          , $5  , $6        , $7  , $8)
                """,
                files,
            )

    async def get_conv(self, msg: EmailMessage) -> Tuple[int, int]:
        conv_actor = None
        # find which conversation this relates to
        in_reply_to = msg['In-Reply-To']
        if in_reply_to:
            conv_actor = await self.conn.fetchrow(
                """
                select a.conv, a.actor from sends
                join actions a on sends.action = a.pk
                where sends.node is null and sends.ref = $1
                order by a.id desc
                limit 1
                """,
                self.clean_msg_id(in_reply_to),
            )

        references = msg['References']
        if not conv_actor and references:
            # try references instead to try and get conv_id
            ref_msg_ids = {self.clean_msg_id(msg_id) for msg_id in references.split(' ') if msg_id}
            if ref_msg_ids:
                conv_actor = await self.conn.fetchrow(
                    """
                    select a.conv, a.actor from sends
                    join actions a on sends.action = a.pk
                    where sends.node is null and sends.ref = any($1)
                    order by a.id desc
                    limit 1
                    """,
                    ref_msg_ids,
                )

        return conv_actor or (None, None)

    def clean_msg_id(self, msg_id):
        msg_id = msg_id.strip('<>\r\n')
        if msg_id.endswith(self.settings.smtp_message_id_domain):
            msg_id = msg_id.split('@', 1)[0]
        return msg_id


to_remove = 'div.gmail_quote', 'div.gmail_extra'  # 'div.gmail_signature'
html_regexes = [
    (re.compile(r'<br/></div><br/>$', re.M), ''),
    (re.compile(r'<br/>$', re.M), ''),
    (re.compile(r'\n{2,}'), '\n'),
]


def get_smtp_body(msg: EmailMessage, message_id: str, existing_conv: bool) -> Tuple[str, bool]:
    m: EmailMessage = msg.get_body(preferencelist=('html', 'plain'))
    if not m:
        raise RuntimeError('email with no content')

    body = m.get_content()
    is_html = m.get_content_type() == 'text/html'
    if is_html and m['Content-Transfer-Encoding'] == 'quoted-printable':
        body = quopri.decodestring(body).decode()

    if not body:
        logger.warning('Unable to find body in email "%s"', message_id)

    if is_html:
        soup = BeautifulSoup(body, 'html.parser')

        if existing_conv:
            # remove the body only if conversation already exists in the db
            for el_selector in to_remove:
                for el in soup.select(el_selector):
                    el.decompose()

        # body = soup.prettify()
        body = str(soup)
        for regex, rep in html_regexes:
            body = regex.sub(rep, body)
    return body, is_html
