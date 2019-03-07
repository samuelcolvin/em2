import logging
from email.message import EmailMessage
from typing import Any, Dict, List, Set

from asyncpg.pool import Pool
from misaka import Markdown, SaferHtmlRenderer

from em2.core import ActionTypes, MsgFormat
from em2.settings import Settings

logger = logging.getLogger('em2.fallback')

flags = ('hard-wrap',)
extensions = ('no-intra-emphasis',)
safe_markdown = Markdown(SaferHtmlRenderer(flags=flags), extensions=extensions)


class BaseFallbackHandler:
    def __init__(self, ctx):
        self.settings: Settings = ctx['settings']
        self.pg: Pool = ctx['pg']

    async def startup(self):  # pragma: no cover
        pass

    async def shutdown(self):  # pragma: no cover
        pass

    async def send_message(self, *, e_from: str, to: Set[str], email_msg: EmailMessage) -> str:
        raise NotImplementedError()

    async def send(self, actions: List[Dict[str, Any]]):  # noqa: 901
        # conv and actor are all the same
        conv_key = actions[0]['conv']
        conv_id = await self.pg.fetchval('select id from conversations where key=$1', conv_key)
        last_action_id = actions[-1]['id']

        if any(a['act'] == ActionTypes.conv_publish for a in actions):
            ctx = await self.on_publish(conv_id, actions)
        elif any(a['act'] == ActionTypes.msg_add for a in actions):
            ctx = await self.on_add_message(conv_id, actions)
        elif any(a['act'] == ActionTypes.prt_add for a in actions):
            ctx = await self.on_add_participants(conv_id, actions)
        else:
            raise NotImplementedError()

        if 'subject' in ctx:
            subject = ctx['subject']
        else:
            subject = await self.pg.fetchval(
                """
                select body from actions
                where conv=$1 and act=any(array['conv:publish', 'conv:create', 'subject:modify']::ActionTypes[])
                """,
                conv_id,
            )

        if 'addresses' in ctx:
            addresses = ctx['addresses']
        else:
            prts = await self.pg.fetch(
                'select u.email from participants p join users u on p.user_id = u.id where p.conv = $1', conv_id
            )
            addresses = [r[0] for r in prts]

        if 'references' in ctx:
            references = ctx['references']
        else:
            msg_ids = await self.pg.fetch(
                'select ref from sends s join actions a on s.action = a.pk where conv = $1 order by a.id desc', conv_id
            )
            references = [r[0] for r in msg_ids]

        if 'in_reply_to' in ctx:
            in_reply_to = ctx['in_reply_to']
        else:
            in_reply_to = references[-1]

        actor = actions[0]['actor']
        to = set(addresses)
        if actor in to:
            to.remove(actor)

        e_msg = EmailMessage()
        e_msg['Subject'] = subject
        e_msg['From'] = actor
        e_msg['To'] = ','.join(to)
        e_msg['EM2-ID'] = f'{conv_key}-{last_action_id}'

        if in_reply_to:
            e_msg['In-Reply-To'] = f'<{in_reply_to}>'
        if references:
            e_msg['References'] = ' '.join(f'<{msg_id}>' for msg_id in references)

        body, msg_format = ctx['body'], ctx['msg_format']
        e_msg.set_content(body)
        if msg_format in {MsgFormat.markdown, MsgFormat.html}:
            html = body
            if msg_format == MsgFormat.markdown:
                html = safe_markdown(html)
            e_msg.add_alternative(html, subtype='html')

        msg_id = await self.send_message(e_from=actor, to=to, email_msg=e_msg)
        logger.info('message sent conv %.6s, smtp message id %0.12s...', conv_key, msg_id)
        await self.pg.fetchval(
            """
            insert into sends (action, ref)
            (select pk, $1 from actions where conv=$2 and id=$3)
            """,
            msg_id,
            conv_id,
            last_action_id,
        )

    async def on_publish(self, conv_id: int, actions: List[Dict[str, Any]]):
        msg_actions = [a for a in actions if a['act'] == ActionTypes.msg_add]
        return dict(
            subject=next(a for a in actions if a['act'] == ActionTypes.conv_publish)['body'],
            body='\n\n'.join(a['body'] for a in msg_actions),
            msg_format=msg_actions[0]['msg_format'],
            addresses=[a['participant'] for a in actions if a['act'] == ActionTypes.prt_add],
            in_reply_to=None,
            references=[],
        )

    async def on_add_message(self, conv_id: int, actions: List[Dict[str, Any]]):
        assert len(actions) == 1, 'expected one action when adding message'
        action = actions[0]
        r = dict(body=action['body'], msg_format=action['msg_format'])
        parent = action.get('parent')
        if parent:
            r['in_reply_to'] = await self.pg.fetchval(
                'select ref from sends where node is null and action=(select pk from actions where id=$1 and conv=$2)',
                parent,
                conv_id,
            )
        return r

    async def on_add_participants(self, conv_id: int, actions: List[Dict[str, Any]]):
        new_participants = ', '.join(
            ['**{}**'.format(a['participant']) for a in actions if a['act'] == ActionTypes.prt_add]
        )
        return dict(
            msg_format=MsgFormat.markdown,
            body=safe_markdown(f'The following people have been added to the conversation: {new_participants}'),
        )
