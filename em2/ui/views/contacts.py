import asyncio

from aiohttp.web import StreamResponse
from atoolbox import get_offset, parse_request_query, raw_json_response
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
        u.profile_status,
        u.profile_status_message
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


class ContactsList(View):
    sql = """
    select json_build_object(
      'items', items,
      'pages', pages
    ) from (
      select coalesce(array_to_json(array_agg(json_strip_nulls(row_to_json(t)))), '[]') items
      from (
        select
          c.id,
          p.email,
          coalesce(c.main_name, p.main_name) main_name,
          coalesce(c.last_name, p.last_name) last_name,
          coalesce(c.strap_line, p.strap_line) strap_line,
          coalesce(c.image_url, p.image_url) image_url,
          coalesce(c.profile_type, p.profile_type) profile_type,
          p.profile_status,
          p.profile_status_message
        from contacts c
        join users p on c.profile_user = p.id
        where :where
        order by coalesce(c.main_name, p.main_name)
        limit 50
        offset :offset
      ) t
    ) items, (
      select (count(*) - 1) / 50 + 1 pages from contacts c where :where
    ) pages
    """

    async def call(self):
        raw_json = await self.conn.fetchval_b(
            self.sql, where=V('c.owner') == self.session.user_id, offset=get_offset(self.request, paginate_by=50)
        )
        return raw_json_response(raw_json)


class ContactDetails(View):
    sql = """
    select json_strip_nulls(row_to_json(contact))
    from (
      select
        c.id,
        c.profile_user user_id,
        p.email,

        c.profile_type c_profile_type,
        c.main_name c_main_name,
        c.last_name c_last_name,
        c.strap_line c_strap_line,
        c.image_url c_image_url,
        c.image_url c_image_url,
        c.body c_body,

        p.visibility p_visibility,
        p.profile_type p_profile_type,
        p.main_name p_main_name,
        p.last_name p_last_name,
        p.strap_line p_strap_line,
        p.image_url p_image_url,
        p.image_url p_image_url,
        coalesce(p.body, 'this is a test') p_body,
        p.profile_status,
        p.profile_status_message
      from contacts c
      join users p on c.profile_user = p.id
      where c.owner=$1 and c.id=$2
    ) contact
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.user_id, int(self.request.match_info['id']))
        return raw_json_response(raw_json)
