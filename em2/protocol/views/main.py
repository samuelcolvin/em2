import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Tuple, Union

import nacl.encoding
from atoolbox import JsonErrors, json_response
from pydantic import BaseModel, EmailStr, Extra, PositiveInt, UrlStr, conint, constr, validator
from typing_extensions import Literal

from em2.background import push_all, push_multiple
from em2.core import (
    Action,
    ActionTypes,
    File,
    UserTypes,
    apply_actions,
    create_conv,
    get_create_multiple_users,
    get_create_user,
)
from em2.protocol.core import HttpError, InvalidSignature
from em2.utils.core import MsgFormat
from em2.utils.storage import check_content_type

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

    def core_files(self) -> Optional[List[File]]:
        pass

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


class ExternalFile(BaseModel):
    hash: constr(min_length=32, max_length=65)
    name: Optional[constr(min_length=1, max_length=1023)]
    content_id: constr(min_length=20, max_length=255)
    content_disp: Literal['attachment', 'inline']
    content_type: constr(max_length=63)
    size: PositiveInt
    download_url: UrlStr

    @validator('content_type')
    def check_content_type(cls, v: str):
        return check_content_type(v)


class MessageAddModel(MessageModel):
    act: Literal[ActionTypes.msg_add]
    files: Optional[List[ExternalFile]] = None

    def core_files(self) -> Optional[List[File]]:
        if self.files:
            return [File(**f.dict()) for f in self.files]


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

    async def execute(self, m: Model):  # noqa: C901 (ignore complexity)
        try:
            em2_node = self.request.query['node']
        except KeyError:
            raise JsonErrors.HTTPBadRequest("'node' get parameter missing")

        try:
            await self.em2.check_signature(em2_node, self.request)
        except InvalidSignature as e:
            msg = e.args[0]
            logger.info('unauthorized em2 push msg="%s" em2-node="%s"', msg, em2_node)
            raise JsonErrors.HTTPUnauthorized(msg)

        actor_emails = {a.actor for a in m.actions}

        # TODO give more details on the problems
        try:
            nodes = set(await asyncio.gather(*[self.em2.get_em2_node(e) for e in actor_emails]))
        except HttpError:
            # this could be temporary due to error get em2 node
            raise JsonErrors.HTTPUnauthorized('not all actors have an em2 nodes')

        if None in nodes:
            # this could be temporary due to an error getting the em2 node
            raise JsonErrors.HTTPUnauthorized('not all actors have an em2 nodes')
        if nodes != {em2_node}:
            raise JsonErrors.HTTPBadRequest("not all actors' em2 nodes match request node")

        file_content_ids = set()
        for a in m.actions:
            if a.act == ActionTypes.msg_add and a.files:
                for f in a.files:
                    if f.content_id in file_content_ids:
                        raise JsonErrors.HTTPBadRequest(f'duplicate file content_id on action {a.id}')
                    file_content_ids.add(f.content_id)

        async with self.conns.main.transaction():
            conv_id, transmit, action_ids = await self.execute_trans(m, em2_node)

        if conv_id is not None:
            if action_ids is None:
                await push_all(self.conns, conv_id, transmit=transmit)
            else:
                await push_multiple(self.conns, conv_id, action_ids, transmit=transmit)

        for content_id in file_content_ids:
            await self.conns.redis.enqueue_job('download_push_file', conv_id, content_id)

    async def execute_trans(self, m: Model, em2_node: str) -> Tuple[Optional[int], bool, Optional[List[int]]]:
        publish_action = next((a for a in m.actions if a.act == ActionTypes.conv_publish), None)
        push_all_actions = False
        if publish_action:
            # is this really the best check, should we just check one of the domains matches?
            are_local = await asyncio.gather(
                *[self.em2.check_local(a.participant) for a in m.actions if a.act == ActionTypes.prt_add]
            )
            if not any(are_local):
                raise JsonErrors.HTTPBadRequest('no participants on this em2 node')
            try:
                await self.published_conv(publish_action, m, em2_node)
                push_all_actions = True
            except JsonErrors.HTTPConflict:
                # conversation already exists, that's okay
                pass

        conversation = self.request.match_info['conv']
        # lock the conversation here so simultaneous requests executing the same action ids won't cause errors
        r = await self.conns.main.fetchrow(
            'select id, last_action_id, leader_node from conversations where key=$1 for no key update', conversation
        )
        if r:
            conv_id, last_action_id, leader_node = r

            if leader_node and leader_node != em2_node:
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
            Action(actor_id=actor_user_ids[a.actor], files=a.core_files(), **a.dict(exclude={'actor', 'files'}))
            for a in actions_to_apply
        ]

        try:
            await apply_actions(self.conns, conv_id, actions)
        except JsonErrors.HTTPNotFound:
            # happens when an actor hasn't yet been added to the conversation, any other times?
            # TODO any other errors?
            raise JsonErrors.HTTPBadRequest('actor does not have permission to update this conversation')

        action_ids = None if push_all_actions else [a.id for a in actions]
        return conv_id, push_transmit, action_ids

    async def published_conv(self, publish_action: PublishModel, m: Model, em2_node: str):
        """
        New conversation just published
        """
        actor_email = publish_action.actor

        actions: List[Action] = []
        actor_id = await get_create_user(self.conns, actor_email, UserTypes.remote_em2)
        for a in m.actions:
            if a.id == publish_action.id:
                actions.append(Action(act=ActionTypes.conv_publish, actor_id=actor_id, id=a.id, ts=a.ts, body=a.body))
                break
            elif a.act == ActionTypes.msg_add:
                actions.append(
                    Action(
                        act=ActionTypes.msg_add,
                        actor_id=actor_id,
                        id=a.id,
                        body=a.body,
                        msg_format=a.msg_format,
                        parent=a.parent,
                        files=a.core_files(),
                    )
                )
            elif a.act == ActionTypes.prt_add and a.participant != actor_email:
                actions.append(Action(act=ActionTypes.prt_add, actor_id=actor_id, id=a.id, participant=a.participant))

        conv_id, _ = await create_conv(
            conns=self.conns,
            creator_email=actor_email,
            actions=actions,
            given_conv_key=self.request.match_info['conv'],
            leader_node=em2_node,
        )
