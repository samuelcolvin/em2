import asyncio
import logging
from asyncio import CancelledError
from typing import Dict

from aiohttp.web_ws import WebSocketResponse
from aioredis import Redis
from buildpg.asyncpg import BuildPgConnection

import ujson
from em2.settings import Settings

logger = logging.getLogger('em2.ui.background')
channel_name = 'actions'


class Background:
    def __init__(self, app):
        self.app = app
        self.settings: Settings = app['settings']
        self.connections: Dict[int, WebSocketResponse] = {}
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self._run())

    def add_ws(self, user_id: int, ws: WebSocketResponse):
        self.connections[user_id] = ws

    def remove_ws(self, user_id: int):
        self.connections.pop(user_id)

    async def _run(self):
        logger.info('starting background task')
        try:
            with await self.app['redis'] as self.redis:
                channel, *_ = await self.redis.psubscribe(channel_name)
                while await channel.wait_message():
                    _, msg = await channel.get()
                    await self.process_action(msg)
        except CancelledError:
            # happens, not a problem
            logger.info('background task got cancelled')
        except Exception as exc:
            logger.exception('exception in background task, %s: %s', exc.__class__.__name__, exc)
            raise

    async def process_action(self, msg: bytes):
        if self.connections:
            data = ujson.loads(msg)
            coros = []
            users = data.pop('users')
            # hack to avoid building json for every use, remove the starting "{" so user_v can be prepended
            msg_json_chunk = ujson.dumps(data)[1:]
            for user_id, user_v in users:
                ws = self.connections.get(user_id)
                if ws is not None:
                    coros.append(self.send(user_id, user_v, ws, msg_json_chunk))

            await asyncio.gather(*coros)

    async def send(self, user_id: int, user_v: int, ws: WebSocketResponse, msg_json_chunk: str):
        msg = '{"user_v": %d,%s' % (user_v, msg_json_chunk)
        try:
            await ws.send_str(msg)
        except (RuntimeError, AttributeError):
            logger.info('websocket "%s" closed (user id %d), removing', ws, user_id)
            self.connections.pop(user_id)


push_sql_template = """
select json_build_object(
  'actions', actions,
  'users', participants,
  'conv_details', conv_details
)
from (
  select array_to_json(array_agg(json_strip_nulls(row_to_json(t)))) as actions
  from (
    select a.id as id, a.act as act, a.ts as ts, actor_user.email as actor,
    a.body as body, a.msg_format as msg_format,
    prt_user.email as participant, follows_action.id as follows, parent_action.id as msg_parent,
    c.key as conv
    from actions as a

    join users as actor_user on a.actor = actor_user.id
    join conversations as c on a.conv = c.id

    left join users as prt_user on a.participant_user = prt_user.id
    left join actions as follows_action on a.follows = follows_action.pk
    left join actions as parent_action on a.msg_parent = parent_action.pk
    {}
  ) as t
) as actions,
(
  select array_to_json(array_agg(t.a)) as participants
  from (
    select array[p.user_id, u.v] as a
    from participants as p
    join conversations as c on p.conv = c.id
    join users u on p.user_id = u.id
    where conv=$1 and (c.published=true or p.user_id=c.creator)
  ) as t
) as participants,
(
  select details as conv_details from conversations where id=$1
) as conv_details
"""

push_sql_all = push_sql_template.format('where a.conv=$1 order by a.id')
push_sql_single = push_sql_template.format('where a.conv=$1 and a.id=$2')


async def push(pg_conn: BuildPgConnection, redis: Redis, conv_id: int, action_id: int, all_actions: bool):
    if all_actions:
        data = await pg_conn.fetchval(push_sql_all, conv_id)
    else:
        data = await pg_conn.fetchval(push_sql_single, conv_id, action_id)
    await redis.publish(channel_name, data)
