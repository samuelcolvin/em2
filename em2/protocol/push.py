import asyncio
import json
import logging
from datetime import datetime
from typing import Any, List, Set, Tuple

from aiohttp import ClientSession
from arq import ArqRedis
from asyncpg.pool import Pool
from cryptography.fernet import Fernet

from em2.core import Action, ActionTypes, UserTypes
from em2.settings import Settings

from .core import Em2Comms, HttpError, actions_to_body

logger = logging.getLogger('em2.push')
RETRY = 'RT'
SMTP = 'SMTP'


async def push_actions(ctx, actions_data: str, users: List[Tuple[str, UserTypes]], **extra: Any):
    pusher = Pusher(ctx)
    return await pusher.push(actions_data, users, **extra)


async def follower_push_actions(ctx, conv_key: str, leader_node: str, interaction_id: str, actions: List[Action]):
    pusher = Pusher(ctx)
    return await pusher.follower_push(conv_key, leader_node, interaction_id, actions)


class Pusher:
    def __init__(self, ctx):
        self.settings: Settings = ctx['settings']
        self.job_try = ctx['job_try']
        self.auth_fernet = Fernet(self.settings.auth_key)
        self.session: ClientSession = ctx['client_session']
        self.pg: Pool = ctx['pg']
        self.redis: ArqRedis = ctx['redis']
        self.em2 = Em2Comms(self.settings, self.session, ctx['signing_key'], self.redis, ctx['resolver'])

    async def push(self, actions_data: str, users: List[Tuple[str, UserTypes]], **extra: Any):
        results = await asyncio.gather(*[self.resolve_user(*u) for u in users])
        retry_users, smtp_addresses, em2_nodes = set(), set(), set()
        for node, email in filter(None, results):
            if node == RETRY:
                retry_users.add((email, False))
            elif node == SMTP:
                smtp_addresses.add(email)
            else:
                em2_nodes.add(node)

        if retry_users:
            await self.redis.enqueue_job(
                'push_actions',
                actions_data,
                retry_users,
                **extra,
                _job_try=self.job_try + 1,
                _defer_by=self.job_try * 10,
            )
        data = json.loads(actions_data)
        conversation, actions = data['conversation'], data['actions']
        if smtp_addresses:
            logger.info('%d smtp emails to send', len(smtp_addresses))
            # "seen" actions don't get sent via SMTP
            # TODO anything else to skip here?
            if not all(a['act'] == ActionTypes.seen for a in actions):
                await self.redis.enqueue_job('smtp_send', conversation, actions)
        if em2_nodes:
            logger.info('%d em2 nodes to push action to', len(em2_nodes))
            await self.em2_send(conversation, actions, em2_nodes, **extra)
        return f'retry={len(retry_users)} smtp={len(smtp_addresses)} em2={len(em2_nodes)}'

    async def follower_push(self, conv_key: str, leader_node: str, interaction_id: str, actions: List[Action]):
        em2_node = self.em2.this_em2_node()
        actions_dicts = await self.action2dict(conv_key, actions)
        to_sign = actions_to_body(conv_key, actions_dicts)
        data = {
            'actions': actions_dicts,
            'upstream_signature': self.em2.signing_key.sign(to_sign).signature.hex(),
            'upstream_em2_node': em2_node,
            'interaction_id': interaction_id,
        }
        try:
            await self.em2.post(f'{leader_node}/v1/follower-push/{conv_key}/', data=data, params={'node': em2_node})
        except HttpError:
            # TODO retry
            raise

    async def action2dict(self, conv_key: str, actions: List[Action]):
        ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        v = await self.pg.fetch(
            """
            select u.id, u.email
            from users u
            join participants p on u.id = p.user_id
            join conversations c on p.conv = c.id
            where c.key=$1 and u.id=any($2)
            """,
            conv_key,
            [a.actor_id for a in actions],
        )
        actor_lookup = {r[0]: r[1] for r in v}
        d = []
        extra_fields = 'body', 'extra_body', 'participant', 'msg_format', 'follows', 'parent', 'files'
        for a in actions:
            d.append(
                {
                    'ts': ts,
                    'act': a.act.value,
                    'actor': actor_lookup[a.actor_id],
                    **{f: getattr(a, f) for f in extra_fields if getattr(a, f) is not None},
                }
            )
        return d

    async def resolve_user(self, email: str, current_user_type: UserTypes):
        if current_user_type == UserTypes.new:
            # only new users are checked to see if they're local
            if await self.em2.check_local(email):
                # local user
                await self.pg.execute("update users set user_type='local' where email=$1", email)
                return

        try:
            em2_node = await self.em2.get_em2_node(email)
        except HttpError:
            # domain has an em2 platform, but request failed, try again later
            return RETRY, email

        if em2_node:
            node = em2_node
            user_type = UserTypes.remote_em2
        else:
            # looks like domain doesn't support em2, smtp
            node = SMTP
            user_type = UserTypes.remote_other

        if current_user_type != user_type:
            await self.pg.execute('update users set user_type=$1, v=null where email=$2', user_type, email)
        return node, email

    async def em2_send(self, conversation: str, actions: List[Any], em2_nodes: Set[str], **extra: Any):
        data = json.dumps({'actions': actions, **extra}).encode()
        this_em2_node = self.em2.this_em2_node()
        await asyncio.gather(*[self.em2_send_node(data, n, this_em2_node, conversation) for n in em2_nodes])

    async def em2_send_node(self, data: bytes, em2_node: str, this_em2_node: str, conversation: str):
        try:
            await self.em2.post(f'{em2_node}/v1/push/{conversation}/', data=data, params={'node': this_em2_node})
        except HttpError:
            # TODO retry
            raise
