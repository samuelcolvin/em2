import asyncio
import logging
from datetime import datetime
from typing import Any, List, Optional, Tuple, Union

import nacl.encoding
from atoolbox import JsonErrors, json_response
from pydantic import BaseModel, EmailStr, Extra, conint, constr, validator
from typing_extensions import Literal

from em2.background import push_all, push_multiple
from em2.core import (
    Action,
    ActionTypes,
    ConvCreateMessage,
    UserTypes,
    apply_actions,
    create_conv,
    get_create_multiple_users,
    get_create_user,
)
from em2.protocol.core import HttpError, InvalidSignature
from em2.utils.core import MsgFormat

from .utils import ExecView

logger = logging.getLogger('em2.protocol.views')


async def signing_verification(request):
    # TODO this could be cached if called a lot
    return json_response(
        keys=[
            {
                'key': request.app['signing_key'].verify_key.encode(encoder=nacl.encoding.HexEncoder).decode(),
                'ttl': 86400,
            }
        ]
    )


class ActionCore(BaseModel):
    id: conint(gt=0)
    ts: datetime
    actor: EmailStr

    class Config:
        extra = Extra.forbid


class ParticipantModel(ActionCore):
    act: Literal[ActionTypes.prt_add]
    participant: EmailStr


class ParticipantRemoveModel(ActionCore):
    act: Literal[ActionTypes.prt_remove]
    participant: EmailStr
    follows: int


class MessageModel(ActionCore):
    body: constr(min_length=1, max_length=10000, strip_whitespace=True)
    extra_body: bool = False
    msg_format: MsgFormat = MsgFormat.markdown
    parent: Optional[int] = None


class MessageAddModel(MessageModel):
    act: Literal[ActionTypes.msg_add]
    warnings: Any = None  # TODO stricter type
    files: list = None  # TODO stricter type


class MessageModifyModel(MessageAddModel):
    act: Literal[ActionTypes.msg_modify]
    follows: int


class PublishModel(ActionCore):
    act: Literal[ActionTypes.conv_publish]
    body: constr(min_length=1, max_length=1000, strip_whitespace=True)
    # for now extra_body is allowed but ignored

    class Config:
        extra = Extra.ignore


class SubjectModifyModel(ActionCore):
    act: Literal[ActionTypes.subject_modify]
    body: constr(min_length=1, max_length=1000, strip_whitespace=True)
    follows: int


follow_only_types = {a for a in ActionTypes if a.value.endswith((':lock', ':release', ':delete'))}
follow_only_types.add(ActionTypes.msg_delete)


class FollowModel(ActionCore):
    act: ActionTypes  # Literal[*lock_release_types]
    follows: int


class Em2Push(ExecView):
    """
    Currently:
    * 200 means ok
    * 400 errors are permanent
    * 401 errors might be temporary
    * 470 specifically means retry with more information
    * everything else should be retried

    Need to formalise this.
    """

    class Model(BaseModel):
        em2_node: constr(min_length=4)
        conversation: str
        actions: List[
            Union[
                ParticipantModel,
                ParticipantRemoveModel,
                MessageAddModel,
                MessageModifyModel,
                PublishModel,
                SubjectModifyModel,
                FollowModel,
            ]
        ]

        @validator('actions', pre=True, whole=True)
        def validate_actions(cls, actions):
            if isinstance(actions, list):
                return list(cls.action_gen(actions))
            raise ValueError('actions must be a list')

        @classmethod
        def action_gen(cls, actions):
            for i, action in enumerate(actions):
                if not isinstance(action, dict):
                    raise ValueError(f'invalid action at index {i}, not dict')

                act = action.get('act')
                if act == ActionTypes.prt_add:
                    yield ParticipantModel(**action)
                elif act == ActionTypes.prt_remove:
                    yield ParticipantRemoveModel(**action)
                elif act == ActionTypes.msg_add:
                    yield MessageAddModel(**action)
                elif act == ActionTypes.msg_modify:
                    yield MessageModifyModel(**action)
                elif act == ActionTypes.conv_publish:
                    yield PublishModel(**action)
                elif act == ActionTypes.subject_modify:
                    yield SubjectModifyModel(**action)
                elif act in follow_only_types:
                    yield FollowModel(**action)
                else:
                    raise ValueError(f'invalid action at index {i}, no support for act {act!r}')

        @validator('actions', whole=True)
        def check_actions(cls, actions):
            if len(actions) == 0:
                raise ValueError('at least one action is required')
            next_action_id = actions[0].id
            for a in actions[1:]:
                next_action_id += 1
                if a.id != next_action_id:
                    raise ValueError('action ids do not increment correctly')

            pub = next((a for a in actions if a.act == ActionTypes.conv_publish), None)
            if pub:
                if actions[0].id != 1:
                    raise ValueError('when publishing, the first action must have ID=1')
                for a in actions:
                    if a.id > pub.id:
                        break
                    elif a.actor != pub.actor:
                        raise ValueError('only a single actor should publish conversations')
                    elif a.act not in {ActionTypes.msg_add, ActionTypes.prt_add, ActionTypes.conv_publish}:
                        raise ValueError(
                            'when publishing, only "participant:add", "message:add" and '
                            '"conv:publish" actions are permitted'
                        )
            return actions

    async def execute(self, m: Model):
        try:
            await self.em2.check_signature(m.em2_node, self.request)
        except InvalidSignature as e:
            msg = e.args[0]
            logger.info('unauthorized em2 push msg="%s" em2-node="%s"', msg, m.em2_node)
            raise JsonErrors.HTTPUnauthorized(msg)

        actor_emails = {a.actor for a in m.actions}

        # TODO give more details on the problems
        try:
            nodes = set(await asyncio.gather(*[self.em2.get_em2_node(e) for e in actor_emails]))
        except HttpError:
            # this could be temporary due to error get em2 node
            raise JsonErrors.HTTPUnauthorized('not all actors have an em2 nodes')

        if None in nodes:
            # this could be temporary due to error get em2 node
            raise JsonErrors.HTTPUnauthorized('not all actors have an em2 nodes')
        if nodes != {m.em2_node}:
            raise JsonErrors.HTTPBadRequest("not all actors' em2 nodes match request node")

        # TODO idempotency key
        async with self.conns.main.transaction():
            conv_id, transmit, action_ids = await self.execute_trans(m)

        if conv_id is not None:
            if action_ids is None:
                await push_all(self.conns, conv_id, transmit=transmit)
            else:
                await push_multiple(self.conns, conv_id, action_ids, transmit=transmit)

    async def execute_trans(self, m: Model) -> Tuple[Optional[int], bool, Optional[List[int]]]:
        publish_action = next((a for a in m.actions if a.act == ActionTypes.conv_publish), None)
        push_all_actions = False
        if publish_action:
            try:
                await self.published_conv(publish_action, m)
                push_all_actions = True
            except JsonErrors.HTTPConflict:
                # conversation already exists, that's okay
                pass

        # lock the conversation here so simultaneous requests executing the same action ids won't cause errors
        r = await self.conns.main.fetchrow(
            'select id, last_action_id, leader_node from conversations where key=$1 for no key update', m.conversation
        )
        if r:
            conv_id, last_action_id, leader_node = r

            if leader_node and leader_node != m.em2_node:
                raise JsonErrors.HTTPBadRequest('request em2 node does not match current em2 node')
        else:
            # conversation doesn't exist and there's no publish_action, need the whole conversation
            raise JsonErrors.HTTP470('full conversation required')  # TODO better error

        actions_to_apply = [a for a in m.actions if a.id > last_action_id]
        push_transmit = leader_node is None
        if not actions_to_apply:
            if push_all_actions:
                return conv_id, push_transmit, None
            else:
                return None, False, None

        if last_action_id + 1 != actions_to_apply[0].id:
            raise JsonErrors.HTTP470('full conversation required')  # TODO better error

        actor_emails = {a.actor for a in m.actions}
        actor_user_ids = await get_create_multiple_users(self.conns, actor_emails)
        actions = [
            Action(actor_id=actor_user_ids[a.actor], **a.dict(exclude={'actor', 'warnings'})) for a in actions_to_apply
        ]

        try:
            await apply_actions(self.conns, conv_id, actions)
        except JsonErrors.HTTPNotFound:
            # happens when an actor hasn't yet been added to the conversation, any other times?
            # TODO any other errors?
            raise JsonErrors.HTTPBadRequest('actor does not have permission to update this conversation')

        action_ids = None if push_all_actions else [a.id for a in actions]
        return conv_id, push_transmit, action_ids

    async def published_conv(self, publish_action: PublishModel, m: Model):
        """
        New conversation just published
        """
        actor_email = publish_action.actor

        messages = []
        participants = {}
        for a in m.actions:
            if a.id > publish_action.id:
                break
            if a.act == ActionTypes.msg_add:
                messages.append(
                    ConvCreateMessage(body=a.body, msg_format=a.msg_format, action_id=a.id, parent=a.parent)
                )
            elif a.act == ActionTypes.prt_add and a.participant != actor_email:
                participants[a.participant] = a.id

        actor_id = await get_create_user(self.conns, actor_email, UserTypes.remote_em2)
        conv_id, _ = await create_conv(
            conns=self.conns,
            creator_email=actor_email,
            creator_id=actor_id,
            subject=publish_action.body,
            publish=True,
            messages=messages,
            participants=participants,
            ts=publish_action.ts,
            given_conv_key=m.conversation,
            leader_node=m.em2_node,
        )
