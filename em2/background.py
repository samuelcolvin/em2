import asyncio
import logging
from asyncio import CancelledError
from typing import Dict, List

import ujson
from aiohttp.abc import Application
from aiohttp.web_ws import WebSocketResponse
from arq.connections import ArqRedis
from buildpg.asyncpg import BuildPgConnection

from em2.core import get_flag_counts
from em2.settings import Settings

logger = logging.getLogger('em2.ui.background')
channel_name = 'actions'


class Background:
    def __init__(self, app: Application):
        self.app = app
        self.settings: Settings = app['settings']
        self.connections: Dict[int, List[WebSocketResponse]] = {}
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self._run())

    def add_ws(self, user_id: int, ws: WebSocketResponse):
        if user_id in self.connections:
            self.connections[user_id].append(ws)
        else:
            self.connections[user_id] = [ws]

    def remove_ws(self, user_id: int, ws: WebSocketResponse):
        wss = self.connections[user_id]
        wss.remove(ws)
        if not wss:
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
            participants = data.pop('participants')
            # hack to avoid building json for every user, remove the ending "}" so extra json can be appended
            msg_json_chunk = ujson.dumps(data)[:-1]
            for p in participants:
                user_id = p.pop('user_id')
                wss = self.connections.get(user_id)
                if wss is not None:
                    coros.append(self.send(user_id, p, wss, msg_json_chunk))

            await asyncio.gather(*coros)

    async def send(self, user_id: int, participant: dict, wss: List[WebSocketResponse], msg_json_chunk: str):
        participant['flags'] = await get_flag_counts(user_id, conn=self.app['pg'], redis=self.app['redis'])
        msg = msg_json_chunk + ',' + ujson.dumps(participant)[1:]
        for ws in wss:
            try:
                await ws.send_str(msg)
            except (RuntimeError, AttributeError):
                logger.info('websocket "%s" closed (user id %d), removing', ws, user_id)
                self.remove_ws(user_id, ws)


local_users_sql = """
select json_build_object(
  'participants', participants,
  'conv_details', conv_details
)
from (
  select array_to_json(array_agg(json_strip_nulls(row_to_json(t)))) as participants
  from (
    select p.user_id, p.spam, p.label_ids as labels, u.v user_v
    from participants as p
    join conversations as c on p.conv = c.id
    join users as u on p.user_id = u.id
    where conv=$1
      and (c.publish_ts is not null or p.user_id=c.creator)
      and (u.user_type = 'new' or u.user_type = 'local')
  ) as t
) as participants,
(
  select details as conv_details from conversations where id=$1
) as conv_details
"""


async def _push_local(pg_conn: BuildPgConnection, redis: ArqRedis, conv_id: int, actions_data: str):
    extra = await pg_conn.fetchval(local_users_sql, conv_id)
    await redis.publish(channel_name, actions_data[:-1] + ',' + extra[1:])


remote_users_sql = """
select u.email, u.user_type
from participants as p
join conversations as c on p.conv = c.id
join users as u on p.user_id = u.id
where conv=$1 and c.publish_ts is not null and u.user_type != 'local'
"""


async def _push_remote(pg_conn: BuildPgConnection, redis: ArqRedis, conv_id: int, actions_data: str):
    remote_users = [tuple(r) for r in await pg_conn.fetch(remote_users_sql, conv_id)]
    if remote_users:
        await redis.enqueue_job('push_actions', actions_data, remote_users)


push_sql_template = """
select json_build_object(
  'actions', actions
)
from (
  select array_to_json(array_agg(json_strip_nulls(row_to_json(t)))) as actions
  from (
    select a.id as id, a.act as act, a.ts as ts, actor_user.email as actor,
    a.body as body, a.msg_format as msg_format,
    prt_user.email as participant, follows_action.id as follows, parent_action.id as parent,
    c.key as conv,
    (select array_agg(row_to_json(f))
      from (
        select content_disp, hash, content_id, name, content_type
        from files
        where files.action = a.pk
      ) f
    ) as files
    from actions as a

    join users as actor_user on a.actor = actor_user.id
    join conversations as c on a.conv = c.id

    left join users as prt_user on a.participant_user = prt_user.id
    left join actions as follows_action on a.follows = follows_action.pk
    left join actions as parent_action on a.parent = parent_action.pk
    {}
  ) as t
) as actions
"""

push_sql_all = push_sql_template.format('where a.conv=$1 order by a.id')
push_sql_multiple = push_sql_template.format('where a.conv=$1 and a.id=any($2)')


async def push_all(pg_conn: BuildPgConnection, redis: ArqRedis, conv_id: int, *, transmit=True):
    actions_data = await pg_conn.fetchval(push_sql_all, conv_id)
    await _push_local(pg_conn, redis, conv_id, actions_data)
    if transmit:
        await _push_remote(pg_conn, redis, conv_id, actions_data)


async def push_multiple(
    pg_conn: BuildPgConnection, redis: ArqRedis, conv_id: int, action_ids: List[int], *, transmit=True
):
    actions_data = await pg_conn.fetchval(push_sql_multiple, conv_id, action_ids)
    await _push_local(pg_conn, redis, conv_id, actions_data)
    if transmit:
        await _push_remote(pg_conn, redis, conv_id, actions_data)
