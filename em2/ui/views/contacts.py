import asyncio

import ujson
from aiohttp.web import StreamResponse
from atoolbox import parse_request_query
from pydantic import BaseModel, constr, validate_email

from .utils import View


class ContactSearch(View):
    response = None

    class Model(BaseModel):
        query: constr(min_length=3, max_length=256, strip_whitespace=True)  # doesn't have to be an email address

    async def call(self):
        # TODO:
        # add strapline, status, and image
        # return a priority for overwriting existing result
        # return a sort ranking
        m = parse_request_query(self.request, self.Model)

        self.response = StreamResponse()
        self.response.content_type = 'application/x-ndjson'
        await self.response.prepare(self.request)

        query = m.query.lower().strip('%')
        try:
            name, email = validate_email(query)
        except ValueError:
            searches = [self.approximate_search(query, query)]
        else:
            searches = [self.approximate_search(email, name)]
        await asyncio.gather(*searches)

        return self.response

    async def write_link(self, email, name=None):
        r = {'email': email}
        if name:
            r['name'] = name
        await self.response.write(ujson.dumps(r).encode() + b'\n')

    async def approximate_search(self, email: str, name: str = None):
        # could in theory use a cursor here, would it help
        # TODO change where "u.email or c.tsv or u.tsv"
        results = await self.conn.fetch(
            """
            select u.email,
            trim(both ' ' from coalesce(c.main_name, u.main_name, '') || ' ' || coalesce(c.last_name, u.last_name, ''))
            from contacts as c
            join users u on u.id = c.profile_user
            where (c.owner=$1 or u.visibility='public-searchable') and u.email like $2
            """,
            self.session.user_id,
            f'%{email}%',
        )
        for email, name in results:
            await self.write_link(email, name)

    async def exact_search(self, email: str):
        r = await self.conn.fetchrow(
            """
            select email, trim(both ' ' from coalesce(main_name || '') || ' ' || coalesce(last_name || ''))
            from users
            where visibility='public' and email=$1
            """,
            email,
        )
        if r:
            await self.write_link(*r)
        else:
            pass
            # TODO check the email address's node for details
