import asyncio
import json
import logging
from typing import Any, Dict, List, Set, Tuple

from aiohttp import ClientSession
from arq import ArqRedis
from asyncpg.pool import Pool
from cryptography.fernet import Fernet

from em2.core import ActionTypes, UserTypes
from em2.settings import Settings

from .core import Em2Comms, HttpError

logger = logging.getLogger('em2.push')
RETRY = 'RT'
SMTP = 'SMTP'


async def push_actions(ctx, actions_data: str, users: List[Tuple[str, UserTypes]]):
    pusher = Pusher(ctx)
    return await pusher.split_destinations(actions_data, users)


class Pusher:
    def __init__(self, ctx):
        self.settings: Settings = ctx['settings']
        self.job_try = ctx['job_try']
        self.auth_fernet = Fernet(self.settings.auth_key)
        self.session: ClientSession = ctx['client_session']
        self.pg: Pool = ctx['pg']
        self.redis: ArqRedis = ctx['redis']
        self.em2 = Em2Comms(self.settings, self.session, ctx['signing_key'], self.redis, ctx['resolver'])

    async def split_destinations(self, actions_data: str, users: List[Tuple[str, UserTypes]]):
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
                'push_actions', actions_data, retry_users, _job_try=self.job_try + 1, _defer_by=self.job_try * 10
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
            await self.em2_send(conversation, actions, em2_nodes)
        return f'retry={len(retry_users)} smtp={len(smtp_addresses)} em2={len(em2_nodes)}'

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

    async def em2_send(self, conversation: str, actions: Dict[str, Any], em2_nodes: Set[str]):
        data = json.dumps({'actions': actions}).encode()
        this_em2_node = self.em2.this_em2_node()
        await asyncio.gather(*[self.em2_send_node(data, n, this_em2_node, conversation) for n in em2_nodes])

    async def em2_send_node(self, data: bytes, em2_node: str, this_em2_node: str, conversation):
        try:
            await self.em2.post(f'{em2_node}/v1/push/{conversation}/', data=data, params={'node': this_em2_node})
        except HttpError:
            # TODO retry
            raise
