from datetime import datetime
from typing import Set

from atoolbox import JsonErrors, parse_request_query, raw_json_response
from pydantic import BaseModel, EmailStr, constr, validator

from em2.core import (
    ActionModel,
    ActionsTypes,
    MsgFormat,
    act,
    construct_conv,
    conv_actions_json,
    draft_conv_key,
    generate_conv_key,
    get_conv_for_user,
    get_create_multiple_users,
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
    class QueryModel(BaseModel):
        since: int = None

    async def call(self):
        m = parse_request_query(self.request, self.QueryModel)
        json_str = await conv_actions_json(self.conn, self.session.user_id, self.request.match_info['conv'], m.since)
        return raw_json_response(json_str)


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
                'insert into participants (conv, user_id) (select $1, unnest($2::int[]))', conv_id, user_ids
            )
            await self.conn.execute(
                """
                insert into actions (conv, act             , actor, ts, participant_user) (
                  select             $1  , 'participant:add', $2  , $3, unnest($4::int[])
                )
                """,
                conv_id,
                creator_id,
                ts,
                user_ids,
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
                ActionsTypes.conv_publish if conv.publish else ActionsTypes.conv_create,
                creator_id,
                ts,
                conv.subject,
            )

        assert publish_id
        # await self.pusher.push(create_action_id, actor_only=True)
        return dict(key=conv_key, status_=201)


class ConvAct(ExecView):
    Model = ActionModel

    async def execute(self, action: Model):
        action_id = await act(self.conn, self.settings, self.session.user_id, self.request.match_info['conv'], action)
        assert action_id
        # await self.pusher.push(action_id, actor_only=True)
        return {'status_': 201, 'action_id': action_id}


class ConvPublish(ExecView):
    class Model(BaseModel):
        publish: bool

        @validator('publish')
        def check_publish(cls, v):
            if not v:
                raise ValueError('publish must be true')
            return v

    async def execute(self, action: Model):
        conv_prefix = self.request.match_info['conv']
        conv_id, last_action, published = await get_conv_for_user(self.conn, self.session.user_id, conv_prefix)
        if last_action:
            # if the usr has be removed from the conversation they can't act
            raise JsonErrors.HTTPNotFound('Conversation not found')
        if published:
            raise JsonErrors.HTTPBadRequest('Conversation already published')

        # could do more efficiently than this, but would require duplicated logic
        conv_summary = await construct_conv(self.conn, self.session.user_id, conv_prefix)
        assert conv_summary

        r = await self.conn.fetch('select user_id from participants where conv=$1', conv_id)
        participant_user_ids = [v[0] for v in r]
        ts = datetime.utcnow()
        async with self.conn.transaction():
            await self.conn.execute('delete from actions where conv=$1', conv_id)
            await self.conn.execute('update conversations set last_action_id=0 where id=$1', conv_id)

            await self.conn.execute(
                """
                insert into actions (conv, act             , actor, ts, participant_user) (
                  select             $1  , 'participant:add', $2  , $3, unnest($4::int[])
                )
                """,
                conv_id,
                self.session.user_id,
                ts,
                participant_user_ids,
            )

            await self.conn.fetchval(
                """
                insert into actions (act, conv, actor)
                values ('conv:publish', $1, $2)
                returning id
                """,
                self.conv_id,
                self.session.user_id,
            )
