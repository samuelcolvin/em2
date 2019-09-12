import logging
import quopri
import re
from datetime import datetime
from email import utils as email_utils
from email.message import EmailMessage
from typing import List, Optional, Set, Tuple

from aiohttp.web_exceptions import HTTPBadRequest
from bs4 import BeautifulSoup
from buildpg.asyncpg import BuildPgConnection

from em2.background import push_all, push_multiple
from em2.core import Action, ActionTypes, Connections, MsgFormat, UserTypes, apply_actions, create_conv, get_create_user
from em2.protocol.core import Em2Comms, HttpError
from em2.utils.smtp import find_smtp_files

logger = logging.getLogger('em2.protocol.views.smtp')

__all__ = ['InvalidEmailMsg', 'remove_participants', 'get_email_recipients', 'process_smtp']


class InvalidEmailMsg(ValueError):
    pass


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


async def get_email_recipients(to: List[str], cc: List[str], message_id: str, conn: BuildPgConnection) -> List[str]:
    # recipients is a unique list of recipients which retains the order from to + cc
    recipients = []
    addr_set = set()
    for _, addr in email_utils.getaddresses(to + cc):
        if addr not in addr_set:
            recipients.append(addr)
            addr_set.add(addr)

    if not recipients:
        logger.warning('email with no recipient, ignoring %s', message_id)
        raise HTTPBadRequest(text='no recipient, ignoring')

    loc_users = await conn.fetchval("select 1 from users where user_type='local' and email=any($1) limit 1", recipients)
    if not loc_users:
        logger.warning('email with no local recipient (%r), ignoring %s', recipients, message_id)
        raise HTTPBadRequest(text='no local recipient, ignoring')
    return recipients


async def process_smtp(
    conns: Connections,
    msg: EmailMessage,
    recipients: List[str],
    storage: str,
    *,
    spam: bool = None,
    warnings: dict = None,
):
    assert not msg['EM2-ID'], 'messages with EM2-ID header should be filtered out before this'
    p = ProcessSMTP(conns)
    await p.run(msg, recipients, storage, spam, warnings)


inline_regex = re.compile(' src')


class ProcessSMTP:
    __slots__ = ('conns',)

    def __init__(self, conns: Connections):
        self.conns: Connections = conns

    async def run(self, msg: EmailMessage, recipients: List[str], storage: str, spam: bool, warnings: dict):
        # TODO deal with non multipart
        _, actor_email = email_utils.parseaddr(msg['From'])
        if not actor_email:
            logger.warning('invalid smtp msg: "From" header', extra={msg: msg})
            raise InvalidEmailMsg('invalid "From" header')
        actor_email = actor_email.lower()

        try:
            message_id = msg['Message-ID'].strip('<> ')
        except AttributeError as e:
            logger.warning('invalid smtp msg (Message-ID): %s', e, exc_info=True, extra={msg: msg})
            raise InvalidEmailMsg('no "Message-ID" header found') from e

        try:
            timestamp = email_utils.parsedate_to_datetime(msg['Date'])
        except (TypeError, ValueError) as e:
            logger.warning('invalid smtp msg (Date) %s: %s', e.__class__.__name__, e, exc_info=True, extra={msg: msg})
            raise InvalidEmailMsg('invalid "Date" header')

        conv_id, original_actor_id = await self.get_conv(msg)
        actor_id = await get_create_user(self.conns, actor_email, UserTypes.remote_other)

        existing_conv = bool(conv_id)
        body, is_html, images = self.get_smtp_body(msg, message_id, existing_conv)
        files = find_smtp_files(msg)
        pg = self.conns.main
        if existing_conv:
            async with pg.transaction():
                existing_prts = await pg.fetch(
                    'select email from participants p join users u on p.user_id=u.id where conv=$1', conv_id
                )
                existing_prts = {r[0] for r in existing_prts}
                if actor_email not in existing_prts:
                    # reply from different address, we need to add the new address to the conversation
                    a = Action(act=ActionTypes.prt_add, participant=actor_email, actor_id=original_actor_id)
                    all_action_ids = await apply_actions(self.conns, conv_id, [a])
                    assert all_action_ids
                else:
                    all_action_ids = []

                # note: this could change the order of new participants to not match the SMTP headers, doesn't matter?
                new_prts = set(recipients) - existing_prts

                msg_format = MsgFormat.html if is_html else MsgFormat.plain
                body = (body or '').strip()
                actions = [
                    Action(act=ActionTypes.msg_add, actor_id=actor_id, body=body, msg_format=msg_format, files=files)
                ]

                actions += [Action(act=ActionTypes.prt_add, actor_id=actor_id, participant=addr) for addr in new_prts]

                action_ids = await apply_actions(self.conns, conv_id, actions, spam=spam, warnings=warnings)
                assert action_ids

                all_action_ids += action_ids
                await pg.execute(
                    'update actions set ts=$1 where conv=$2 and id=any($3)', timestamp, conv_id, all_action_ids
                )
                send_id, add_action_pk = await pg.fetchrow(
                    """
                    insert into sends (action, ref, complete, storage)
                    (select pk, $1, true, $2 from actions where conv=$3 and id=any($4) and act='message:add' limit 1)
                    returning id, action
                    """,
                    message_id,
                    storage,
                    conv_id,
                    action_ids,
                )
                await pg.execute('update files set send=$1 where action=$2', send_id, add_action_pk)
                await push_multiple(self.conns, conv_id, action_ids, transmit=False)
        else:
            async with pg.transaction():
                actions = [Action(act=ActionTypes.prt_add, actor_id=actor_id, participant=r) for r in recipients]

                actions += [
                    Action(
                        act=ActionTypes.msg_add,
                        actor_id=actor_id,
                        body=body.strip(),
                        msg_format=MsgFormat.html if is_html else MsgFormat.plain,
                        files=files,
                    ),
                    Action(act=ActionTypes.conv_publish, actor_id=actor_id, ts=timestamp, body=msg['Subject'] or '-'),
                ]
                conv_id, conv_key = await create_conv(
                    conns=self.conns,
                    creator_email=actor_email,
                    actions=actions,
                    spam=spam,
                    warnings=warnings,
                    live=False,
                )
                send_id, add_action_pk = await pg.fetchrow(
                    """
                    insert into sends (action, ref, complete, storage)
                    (select pk, $1, true, $2 from actions where conv=$3 and act='message:add' limit 1)
                    returning id, action
                    """,
                    message_id,
                    storage,
                    conv_id,
                )
                await pg.execute('update files set send=$1 where action=$2', send_id, add_action_pk)
            await self.conns.redis.enqueue_job('post_receipt', conv_id)

        if images:
            await self.conns.redis.enqueue_job('get_images', conv_id, add_action_pk, images)

    async def get_conv(self, msg: EmailMessage) -> Tuple[int, int]:
        conv_actor = None
        # find which conversation this relates to
        in_reply_to = msg['In-Reply-To']
        if in_reply_to:
            conv_actor = await self.conns.main.fetchrow(
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
                conv_actor = await self.conns.main.fetchrow(
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
        if msg_id.endswith(self.conns.settings.smtp_message_id_domain):
            msg_id = msg_id.split('@', 1)[0]
        return msg_id

    def get_smtp_body(self, msg: EmailMessage, message_id: str, existing_conv: bool) -> Tuple[str, bool, Set[str]]:
        m: EmailMessage = msg.get_body(preferencelist=('html', 'plain'))
        if not m:
            raise RuntimeError('email with no content')

        body = m.get_content()
        is_html = m.get_content_type() == 'text/html'
        if is_html and m['Content-Transfer-Encoding'] == 'quoted-printable':
            # are there any other special characters to remove?
            body = quopri.decodestring(body.replace('\xa0', '')).decode()

        if not body:
            logger.warning('Unable to find body in email "%s"', message_id)

        images = set()
        if is_html:
            body, images = self.parse_html(body, existing_conv)
        return body, is_html, images

    def parse_html(self, body: str, existing_conv: bool) -> Tuple[str, Set[str]]:
        soup = BeautifulSoup(body, 'html.parser')

        if existing_conv:
            # remove the body only if conversation already exists in the db
            for el_selector in to_remove:
                for el in soup.select(el_selector):
                    el.decompose()

        # find images
        images = [img['src'] for img in soup.select('img') if src_url_re.match(img['src'])]

        for style in soup.select('style'):
            images += [m.group(2) for m in style_url_re.finditer(style.string)]

        # do it like this as we want to take the first max_ref_image_count unique images
        image_set = set()
        for image in images:
            if image not in image_set:
                image_set.add(image)
                if len(image_set) >= self.conns.settings.max_ref_image_count:
                    break

        # body = soup.prettify()
        body = str(soup)
        for regex, rep in html_regexes:
            body = regex.sub(rep, body)

        return body, image_set


to_remove = 'div.gmail_quote', 'div.gmail_extra'  # 'div.gmail_signature'
style_url_re = re.compile(r'\surl\(([\'"]?)((?:https?:)?//.+?)\1\)', re.I)
src_url_re = re.compile(r'(?:https?:)?//', re.I)
html_regexes = [
    (re.compile(r'<br/></div><br/>$', re.M), ''),
    (re.compile(r'<br/>$', re.M), ''),
    (re.compile(r'\n{2,}'), '\n'),
]


async def post_receipt(ctx, conv_id: int):
    """
    run after receiving a conversation: decide on leader, set live and notify
    """
    async with ctx['pg'].acquire() as conn:
        leader = await get_leader(ctx, conv_id, conn)
        await conn.execute('update conversations set live=true, leader_node=$1 where id=$2', leader, conv_id)

        conns = Connections(conn, ctx['redis'], ctx['settings'])
        await push_all(conns, conv_id, transmit=False)


async def get_leader(ctx, conv_id: int, pg: BuildPgConnection) -> Optional[str]:
    """
    Iterate over participants in the conversation (except the creator) and find the first one which is either local
    or associated with another em2 node, return that node as leader (None if local).
    """
    em2 = Em2Comms(ctx['settings'], ctx['client_session'], ctx['signing_key'], ctx['redis'], ctx['resolver'])

    prt_users = await pg.fetch(
        """
        select u.email, u.user_type from users u
        join participants p on u.id = p.user_id
        where p.conv=$1 and u.user_type != 'remote_other'
        order by p.id
        """,
        conv_id,
    )
    for email, user_type in prt_users:
        if user_type == UserTypes.local:
            # this node is leader
            return
        elif user_type == UserTypes.new:
            if await em2.check_local(email):
                await pg.execute("update users set user_type='local' where email=$1", email)
                return

        try:
            em2_node = await em2.get_em2_node(email)
        except HttpError:
            # domain has an em2 platform, but request failed, have to assume this isn't the leader
            # TODO this could cause problems where different nodes assume different leaders
            continue

        new_user_type = UserTypes.remote_em2 if em2_node else UserTypes.remote_other
        if user_type != new_user_type:
            await pg.execute('update users set user_type=$1, v=null where email=$2', new_user_type, email)
        if em2_node:
            return em2_node

    logger.warning('unable to select leader for conv %d, no participants are using em2 or are local', conv_id)
    # will default to self as leader which is the least bad solution
