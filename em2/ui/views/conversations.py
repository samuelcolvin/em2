from datetime import datetime
from typing import Set

from atoolbox import JsonErrors, parse_request_query, raw_json_response
from buildpg import V
from pydantic import BaseModel, EmailStr, constr, validator

from em2.core import (
    ActionsTypes,
    MsgFormat,
    Relationships,
    draft_conv_key,
    generate_conv_key,
    get_conv_for_user,
    get_create_multiple_users,
    get_create_user,
)

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
      select a.id as id, act, a.ts as ts, actor_user.email as actor,
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
        conv_id, last_action = await get_conv_for_user(self.conn, self.session.user_id, self.request.match_info['conv'])
        where_logic = V('a.conv') == conv_id
        if last_action:
            where_logic &= V('a.id') <= last_action

        m = parse_request_query(self.request, self.QueryModel)
        if m.since:
            await self.fetchval404('select 1 from actions where conv=$1 and id=$1', conv_id, m.since)
            where_logic &= V('a.id') > m.since

        json_str = await self.conn.fetchval_b(self.actions_sql, where=where_logic)
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
                insert into actions (conv, act, actor, ts, participant) (
                  select $1, 'participant:add', $3, $4, p from parts
                )
                """,
                conv_id,
                user_ids,
                creator_id,
                ts,
            )
            await self.conn.execute(
                """
                insert into actions (conv, act          , actor, ts, body, msg_format)
                values              ($1  , 'message:add', $2   , $3, $4  , $5)
                """,
                conv_id,
                creator_id,
                ts,
                conv.message,
                conv.msg_format,
            )
            publish_id = await self.conn.fetchrow(
                """
                insert into actions (conv, act, actor, ts, body)
                values              ($1  , $2 , $3   , $4, $5)
                returning id
                """,
                conv_id,
                'conv:publish' if conv.publish else 'conv:create',
                creator_id,
                ts,
                conv.subject,
            )

        assert publish_id
        # await self.pusher.push(create_action_id, actor_only=True)
        return dict(key=conv_key, status_=201)


prt_action_types = {ActionsTypes.prt_add, ActionsTypes.prt_remove, ActionsTypes.prt_modify}


class ConvAct(ExecView):
    class Model(BaseModel):
        act: ActionsTypes
        participant: EmailStr = None
        body: str = None
        msg_follows: int = None
        msg_relationship: Relationships = None
        msg_format: MsgFormat = None

        @validator('act')
        def check_act(cls, v):
            if v in {ActionsTypes.conv_publish, ActionsTypes.conv_publish}:
                raise ValueError('Action not permitted')

        @validator('participant', always=True)
        def check_participant(cls, v, values, **kwargs):
            act: ActionsTypes = values['act']
            if v and act not in prt_action_types:
                raise ValueError('participant must be set for participant:* actions')
            if not v and act in prt_action_types:
                raise ValueError('participant can only be used with participant:* actions')

    async def execute(self, action: Model):
        # TODO perhaps this logic could be shared with protocol?
        conv_id, last_action = await get_conv_for_user(self.conn, self.session.user_id, self.request.match_info['conv'])
        if last_action:
            raise JsonErrors.HTTPNotFound(message='Conversation not found')

        action_id = None
        if action.act in prt_action_types:
            action_id = await self._act_on_participant(conv_id, action)
        assert action_id

    async def _act_on_participant(self, conv_id, action: Model):
        if action.act == ActionsTypes.prt_add:
            new_user_id = await get_create_user(self.conn, action.participant)
            prt_id = await self.conn.fetchval(
                """
                insert into participants (conv, user_id) values ($1, $2)
                on conflict (conv, user_id) do nothing returning id
                """,
                conv_id,
                new_user_id,
            )
            if not prt_id:
                raise JsonErrors.HTTPConflict(error='user already a participant in this conversation')
        elif action.act == ActionsTypes.prt_remove:
            prt_id = await self.conn.fetchval(
                """
                select p.id from participants as p join users as u on p.user_id = u.id
                where conv=$1 and email=$2
                """,
                conv_id,
                action.participant,
            )
            if not prt_id:
                raise JsonErrors.HTTPNotFound('user not found on conversation')
            await self.conn.execute('delete from participants where id=$1', prt_id)
        else:
            raise NotImplementedError('"participant:modify" not yet implemented')
        return await self.conn.fetchval(
            """
            insert into actions (conv, act, actor, participant)
            values ($1, $2, $3, $5) returning id
            """,
            conv_id,
            action.act,
            self.session.user_id,
            prt_id,
        )
