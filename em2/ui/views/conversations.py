from datetime import datetime

from atoolbox import raw_json_response, JsonErrors
from buildpg import V, funcs
from pydantic import constr, EmailStr, BaseModel
from typing import Set, List

from utils.db import create_missing_recipients, generate_conv_key, gen_random
from .utils import ExecView, View


class ConvList(View):
    sql = """
    select array_to_json(array_agg(row_to_json(t)), true)
    from (
      select c.key as key, c.subject as subject, c.created_ts as created_ts, c.updated_ts as updated_ts,
        c.published as published, c.snippet as snippet
      from conversations as c
      left join participants on c.id = participants.conv
      where participants.recipient=$1
      order by c.created_ts, c.id desc
      limit 50
    ) t;
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.recipient_id)
        return raw_json_response(raw_json or '[]')


class ConvActions(ExecView):
    get_conv_sql = """
    select c.id, c.published, c.creator from conversations as c
    join participants as p on c.id=p.conv
    where p.recipient=$1 and c.key like $2
    order by c.created_ts desc
    limit 1
    """
    # used when the recipient was part of the conversation, but got removed
    get_conv_was_deleted_sql = """
    select c.id, c.published, c.creator, a.id from actions as a
    join conversations as c on a.conv = c.id
    where a.recipient=$1 and c.key like $2 and a.component='participant' and a.verb='delete'
    order by c.created_ts desc, a.id desc
    limit 1
    """

    actions_sql = """
    select array_to_json(array_agg(row_to_json(t)), true)
    from (
      select a.key as key, a.verb as verb, a.component as component, a.body as body, a.timestamp as timestamp,
      actor_recipient.address as actor,
      a_parent.key as parent,
      m.key as message,
      prt_recipient.address as participant
      from actions as a

      left join actions as a_parent on a.parent = a_parent.id
      left join messages as m on a.message = m.id

      join recipients as actor_recipient on a.actor = actor_recipient.id

      left join recipients as prt_recipient on a.recipient = prt_recipient.id
      where :where
      order by a.id
    ) t;
    """

    action_id_sql = 'select id from actions where conv=$1 and key=$2'

    async def call(self):
        conv_key = self.request.match_info['conv'] + '%'
        r = await self.conn.fetchrow(self.get_conv_sql, self.session.recipient_id, conv_key + '%')
        where_logic: List[V] = []
        if r:
            conv_id, published, creator = r
        else:
            # can happen legitimately when they were deleted from the conversation
            conv_id, published, creator, last_action = await self.fetchrow404(
                self.get_conv_was_deleted_sql,
                self.session.recipient_id, conv_key + '%',
            )
            where_logic.append(V('a.id') <= last_action)

        if not published and self.session.recipient_id != creator:
            raise JsonErrors.HTTPForbidden(error='conversation is unpublished and you are not the creator')

        since_action = self.request.query.get('since')
        if since_action:
            first_action_id = await self.fetchval404(self.action_id_sql, conv_id, since_action)
            where_logic.append(V('a.id') > first_action_id)

        json_str = await self.conn.fetchval_b(self.actions_sql, where=funcs.AND(*where_logic))
        return raw_json_response(json_str or '[]')


async def publish_create(conn, creator_id, conv_id, subject, recip_ids, publish):
    create_msg_action_sql = """
    insert into actions (key, conv, actor, message, body,   component, verb)
    select               $1,  $2,   $3,    m.id,    m.body, 'message', 'add'
    from messages as m
    where m.conv=$2
    limit 1
    returning id
    """
    create_prt_action_sql = """
    insert into actions (key, conv, actor, recipient, parent, component,     verb)
    values              ($1,  $2,   $3,    $4,        $5,     'participant', 'add')
    returning id
    """
    create_action_sql = """
    insert into actions (key, conv, actor, body, parent, verb)
    values              ($1,  $2,   $3,    $4,   $5,     $6  )
    returning id
    """
    parent_id = await conn.fetchval(
        create_msg_action_sql,
        gen_random('act'),
        conv_id,
        creator_id,
    )
    for recipient in recip_ids:
        parent_id = await conn.fetchval(
            create_prt_action_sql,
            gen_random('act'),
            conv_id,
            creator_id,
            recipient,
            parent_id,
        )
    verb = 'publish' if publish else 'create'
    return await conn.fetchval(
        create_action_sql,
        gen_random(verb[:3]),
        conv_id,
        creator_id,
        subject,
        parent_id,
        verb,
    )


class ConvCreate(ExecView):
    create_conv_sql = """
    insert into conversations (key, creator, subject, published, created_ts, updated_ts)
    values                    ($1,  $2,      $3,      $4       , $5        , $5        )
    on conflict (key) do nothing
    returning id
    """
    add_participants_sql = 'insert into participants (conv, recipient) values ($1, $2)'
    add_message_sql = 'insert into messages (conv, key, body) values ($1, $2, $3)'

    class Model(BaseModel):
        subject: constr(max_length=255, strip_whitespace=True)
        message: constr(max_length=2047, strip_whitespace=True)
        participants: Set[EmailStr] = set()
        publish = False

    async def execute(self, conv: Model):
        conv.participants.add(self.session.address)
        recip_ids = await create_missing_recipients(self.conn, conv.participants)

        ts = datetime.utcnow()
        conv_key = generate_conv_key(self.session.address, ts, conv.subject) if conv.publish else gen_random('dft')
        msg_key = gen_random('msg')
        async with self.conn.transaction():
            conv_id = await self.conn.fetchval(
                self.create_conv_sql,
                conv_key, self.session.recipient_id, conv.subject, conv.publish, ts
            )
            if conv_id is None:
                raise JsonErrors.HTTPConflict(error='key conflicts with existing conversation')
            await self.conn.executemany(self.add_participants_sql, {(conv_id, rid) for rid in recip_ids})
            await self.conn.execute(self.add_message_sql, conv_id, msg_key, conv.message)

            create_action_id = await publish_create(self.conn, self.session.recipient_id,
                                                    conv_id, conv.subject, recip_ids, conv.publish)

        assert create_action_id
        # await self.pusher.push(create_action_id, actor_only=True)
        return dict(key=conv_key, status_=201)
