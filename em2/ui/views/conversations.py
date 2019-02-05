from datetime import datetime
from typing import List, Set

from atoolbox import JsonErrors, parse_request_query, raw_json_response
from buildpg import V, funcs
from pydantic import BaseModel, EmailStr, constr

from em2.core import MsgFormat, draft_conv_key, generate_conv_key, get_create_multiple_users

from .utils import ExecView, View


class ConvList(View):
    # TODO add count (max 999)
    sql = """
    select array_to_json(array_agg(row_to_json(t)), true)
    from (
      select key, created_ts, updated_ts, published, details
      from conversations as c
      left join participants on c.id = participants.conv
      where participants.user_id=$1
      order by c.created_ts, c.id desc
      limit 50
    ) t;
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.user_id)
        return raw_json_response(raw_json or '[]')


class ConvActions(View):
    actions_sql = """
    select array_to_json(array_agg(json_strip_nulls(row_to_json(t))), true)
    from (
      select a.id as id, verb, component, a.ts as ts, actor_user.email as actor,
      body, msg_follows, msg_relationship, msg_format, prt_user.email as participant
      from actions as a

      join users as actor_user on a.actor = actor_user.id

      left join participants as p on a.participant = p.id
      left join users as prt_user on p.user_id = prt_user.id
      where :where
      order by a.id
    ) t;
    """

    class QueryModel(BaseModel):
        since: int = None

    async def call(self):
        conv_key = self.request.match_info['conv'] + '%'
        where_logic: List[V] = []
        r = await self.conn.fetchrow(
            """
            select c.id, c.published, c.creator from conversations as c
            join participants as p on c.id=p.conv
            where p.user_id=$1 and c.key like $2
            order by c.created_ts desc
            limit 1
            """,
            self.session.user_id,
            conv_key,
        )
        if r:
            conv_id, published, creator = r
        else:
            # can happen legitimately when a user was removed from the conversation,
            # but can still view it up to that point
            conv_id, published, creator, last_action = await self.fetchrow404(
                """
                select c.id, c.published, c.creator, a.id from actions as a
                join conversations as c on a.conv = c.id
                join participants as p on a.participant = p.id
                where p.user_id=$1 and c.key like $2 and a.component='participant' and a.verb='remove'
                order by c.created_ts desc, a.id desc
                limit 1
                """,
                self.session.user_id,
                conv_key,
            )
            where_logic.append(V('a.id') <= last_action)

        if not published and self.session.user_id != creator:
            raise JsonErrors.HTTPForbidden(error='conversation is unpublished and you are not the creator')

        m = parse_request_query(self.request, self.QueryModel)
        if m.since:
            await self.fetchval404('select 1 from actions where conv=$1 and id=$1', conv_id, m.since)
            where_logic.append(V('a.id') > m.since)

        where_logic.append(V('a.conv') == conv_id)
        json_str = await self.conn.fetchval_b(self.actions_sql, where=funcs.AND(*where_logic))
        return raw_json_response(json_str or '[]')


class ConvCreate(ExecView):
    class Model(BaseModel):
        subject: constr(max_length=255, strip_whitespace=True)
        message: constr(max_length=2047, strip_whitespace=True)
        participants: Set[EmailStr] = set()
        msg_format: MsgFormat = MsgFormat.markdown
        publish = False

    async def execute(self, conv: Model):
        ts = datetime.utcnow()
        conv_key = generate_conv_key(self.session.email, ts, conv.subject) if conv.publish else draft_conv_key()
        creator_id = self.session.user_id
        async with self.conn.transaction():
            conv_id = await self.conn.fetchval(
                """
                insert into conversations (key, creator, published, created_ts, updated_ts)
                values                    ($1,  $2     , $3       , $4        , $4        )
                on conflict (key) do nothing
                returning id
                """,
                conv_key,
                creator_id,
                conv.publish,
                ts,
            )
            if conv_id is None:
                raise JsonErrors.HTTPConflict(error='key conflicts with existing conversation')

            part_users = await get_create_multiple_users(self.conn, conv.participants)
            user_ids = [creator_id] + list(part_users.values())

            await self.conn.execute(
                """
                with parts as (
                  insert into participants (conv, user_id) (select $1, unnest ($2::int[])) returning id as p
                )
                insert into actions (conv, verb, component, actor, participant) (
                  select $1, 'add', 'participant', $3, p from parts
                )
                """,
                conv_id,
                user_ids,
                creator_id,
            )
            await self.conn.execute(
                """
                insert into actions (conv, verb , component, actor, body, msg_format)
                values              ($1,   'add', 'message', $2   , $3  , $4)
                """,
                conv_id,
                creator_id,
                conv.message,
                conv.msg_format,
            )
            publish_id = await self.conn.fetchrow(
                """
                insert into actions (conv, verb, component, actor, ts, body)
                values              ($1  ,  $2 , 'conv'   , $3   , $4, $5)
                returning id
                """,
                conv_id,
                'publish' if conv.publish else 'add',
                creator_id,
                ts,
                conv.subject,
            )
            await self.conn.execute('update actions set ts=$2 where conv=$1', conv_id, ts)

        assert publish_id
        # await self.pusher.push(create_action_id, actor_only=True)
        return dict(key=conv_key, status_=201)
