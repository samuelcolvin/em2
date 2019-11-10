import asyncio

from aiohttp.web import StreamResponse
from atoolbox import parse_request_query
from buildpg import V, funcs
from pydantic import BaseModel, constr, validate_email, validator

from em2.search import build_query_function

from .utils import View


class ContactSearch(View):
    response = None
    search_sql = """
    select json_strip_nulls(row_to_json(t)) from (
      select
        u.email,
        c.id is not null is_contact,
        coalesce(c.main_name, u.main_name) main_name,
        coalesce(c.last_name, u.last_name) last_name,
        coalesce(c.strap_line, u.strap_line) strap_line,
        coalesce(c.image_url, u.image_url) image_url,
        coalesce(c.profile_status, u.profile_status) profile_status,
        coalesce(c.profile_status_message, u.profile_status_message) profile_status_message
      from users u
      left join contacts c on u.id = c.profile_user
      where u.id != :this_user and :where
    ) t
    """

    class Model(BaseModel):
        query: constr(min_length=3, max_length=256, strip_whitespace=True)

        @validator('query')
        def strip_percent(cls, v):
            return v.strip('%')

    async def call(self):
        m = parse_request_query(self.request, self.Model)

        self.response = StreamResponse()
        self.response.content_type = 'application/x-ndjson'
        await self.response.prepare(self.request)

        email = None
        try:
            _, email = validate_email(m.query)
        except ValueError:
            pass
        else:
            where = funcs.AND(
                V('email') == email.lower(),
                funcs.OR(
                    V('c.owner') == self.session.user_id,
                    V('u.visibility') == 'public',
                    V('u.visibility') == 'public-searchable',
                ),
            )
            json_str = await self.conn.fetchval_b(self.search_sql, this_user=self.session.user_id, where=where)
            if json_str:
                await self.write_line(json_str)
                # got an exact result, no need to go further
                return self.response

        await asyncio.gather(self.tsvector_search(m), self.partial_email_search(m))

        if email:
            pass
            # TODO look up node for email domain
        return self.response

    async def write_line(self, json_str: str):
        await self.response.write(json_str.encode() + b'\n')

    async def tsvector_search(self, m: Model):
        query_func = build_query_function(m.query)
        where = funcs.AND(
            funcs.OR(V('u.vector').matches(query_func), V('c.vector').matches(query_func)),
            funcs.OR(V('c.owner') == self.session.user_id, V('u.visibility') == 'public-searchable'),
        )
        q = await self.conn.fetch_b(self.search_sql, this_user=self.session.user_id, where=where)
        for r in q:
            await self.write_line(r[0])

    async def partial_email_search(self, m: Model):
        if ' ' in m.query:
            return
        # could be a partial email address
        where = funcs.AND(
            V('email').like(f'%{m.query.lower()}%'),
            funcs.OR(V('c.owner') == self.session.user_id, V('u.visibility') == 'public-searchable'),
        )
        # use a different connection to avoid conflicting with tsvector_search
        pg = self.request.app['pg']
        q = await pg.fetch_b(self.search_sql, this_user=self.session.user_id, where=where)
        for r in q:
            await self.write_line(r[0])
