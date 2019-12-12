import asyncio
from typing import List, Tuple

from buildpg import Values
from buildpg.asyncpg import BuildPgPool
from pydantic import BaseModel, constr
from typing_extensions import Literal

from em2.settings import Settings

from .core import Em2Comms, HttpError


async def update_profiles(ctx, users: List[Tuple[int, str]]):
    updater = ContactUpdate(ctx)
    return await updater.update(users)


class ProfileModel(BaseModel):
    profile_type: Literal['personal', 'work', 'organisation']
    visibility: Literal['public', 'public-searchable']
    main_name: constr(max_length=63)
    last_name: constr(max_length=63) = None
    strap_line: constr(max_length=127) = None
    image_url: constr(max_length=2047) = None
    profile_status: Literal['active', 'away', 'dormant']
    profile_status_message: constr(max_length=511) = None
    details: constr(max_length=5000) = None


class ContactUpdate:
    def __init__(self, ctx):
        self.settings: Settings = ctx['settings']
        self.pg: BuildPgPool = ctx['pg']
        # self.redis: ArqRedis = ctx['redis']
        self.em2 = Em2Comms(self.settings, ctx['client_session'], ctx['signing_key'], ctx['redis'], ctx['resolver'])

    async def update(self, users):
        this_em2_node = self.em2.this_em2_node()
        await asyncio.gather(*[self.update_user(user_id, email, this_em2_node) for user_id, email in users])

    async def update_user(self, user_id: int, email: str, this_em2_node: str):
        try:
            em2_node = await self.em2.get_em2_node(email)
            r = await self.em2.get(
                f'{em2_node}/v1/profile/',
                model=ProfileModel,
                params={'email': email, 'node': this_em2_node},
                expected_statuses=(200, 404),
                model_response=(200,),
            )
        except HttpError:
            # TODO retry
            raise

        if r.status == 200:
            await self.update_db(user_id, r.model)

    async def update_db(self, user_id: int, model: ProfileModel):
        await self.pg.execute_b(
            """
            update users set
              update_ts=now(),
              vector=setweight(to_tsvector(:name), 'A') ||
                     setweight(to_tsvector(:strap_line), 'B') ||
                     to_tsvector(:details),
              :values
            where  id=:user_id
            """
            "",
            values=Values(**model.dict()),
            name=f'{model.main_name} {model.last_name or ""}',
            strap_line=model.strap_line,
            details=model.details and model.details[:500],
            user_id=user_id,
        )
