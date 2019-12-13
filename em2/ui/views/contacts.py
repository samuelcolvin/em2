import asyncio
from typing import List, Optional, Tuple
from uuid import UUID, uuid4

import ujson
from aiohttp.web import StreamResponse
from aiohttp.web_exceptions import HTTPNotImplemented
from asyncpg import Record
from atoolbox import JsonErrors, get_offset, json_response, parse_request_json_ignore_missing, parse_request_query
from buildpg import SetValues, V, Values, funcs
from pydantic import BaseModel, EmailStr, conint, constr, validate_email, validator
from typing_extensions import Literal

from em2.search import build_query_function
from em2.utils.storage import S3, S3Client, image_extensions, parse_storage_uri, set_image_url

from ...settings import Settings
from ...utils import listify
from ...utils.images import InvalidImage, resize_image
from .utils import ExecView, View


class ContactSearch(View):
    """
    Used when adding new participants to a conversation.
    """

    response = None
    search_sql = """
    select
      u.email,
      c.id is not null is_contact,
      coalesce(c.main_name, u.main_name) main_name,
      coalesce(c.last_name, u.last_name) last_name,
      coalesce(c.strap_line, u.strap_line) strap_line,
      coalesce(c.thumb_storage, u.thumb_storage) image_storage,
      coalesce(c.profile_type, u.profile_type) profile_type,
      u.profile_status,
      u.profile_status_message
    from users u
    left join contacts c on u.id = c.profile_user
    where u.id != :this_user and :where
    """

    class Model(BaseModel):
        query: constr(min_length=3, max_length=256, strip_whitespace=True)

        @validator('query')
        def strip_percent(cls, v):
            return v.strip('%')

    async def call(self):
        m = parse_request_query(self.request, self.Model)

        self.response = StreamResponse()
        self.response.content_type = 'text/plain'
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
            r = await self.conn.fetchrow_b(self.search_sql, this_user=self.session.user_id, where=where)
            if r:
                await self.write_line(r)
                # got an exact result, no need to go further
                return self.response

        await asyncio.gather(self.tsvector_search(m), self.partial_email_search(m))

        if email:
            pass
            # TODO look up node for email domain
        return self.response

    async def write_line(self, row: Record):
        await self.response.write(ujson.dumps(set_image_url(row, self.settings)).encode() + b'\n')

    async def tsvector_search(self, m: Model):
        query_func = build_query_function(m.query)
        where = funcs.AND(
            funcs.OR(V('u.vector').matches(query_func), V('c.vector').matches(query_func)),
            funcs.OR(V('c.owner') == self.session.user_id, V('u.visibility') == 'public-searchable'),
        )
        q = await self.conn.fetch_b(self.search_sql, this_user=self.session.user_id, where=where)
        for r in q:
            await self.write_line(r)

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
            await self.write_line(r)


class ContactEmailLookup(View):
    """
    Look up user and contact details by one or more email addresses.
    """

    class QueryModel(BaseModel):
        email: List[EmailStr]

        @validator('email', each_item=True)
        def lower_emails(cls, v):
            return v.lower()

    sql = """
    select
      u.email,
      coalesce(full_name(c.main_name, c.last_name), full_name(u.main_name, u.last_name)) as name,
      coalesce(c.strap_line, u.strap_line) strap_line,
      coalesce(c.thumb_storage, u.thumb_storage) image_storage,
      coalesce(c.profile_type, u.profile_type) profile_type,
      u.profile_status,
      u.profile_status_message,
      c.id contact_id,
      c.v
    from users u
    left join contacts c on c.profile_user=u.id and c.owner=$1
    where email=any($2) and (c.id is not null or u.visibility = any('{public-searchable,public}'))
    """

    async def call(self):
        # can't currently use raw sql here due to signing download urls
        m = parse_request_query(self.request, self.QueryModel)
        users = {}
        for r in await self.conn.fetch(self.sql, self.session.user_id, m.email):
            u = set_image_url(r, self.settings)
            email = u.pop('email')
            if u:
                # no point in returning users with no information
                users[email] = u
        return json_response(**users)


class ContactsList(View):
    items_sql = """
    select
      c.id,
      p.email,
      coalesce(c.main_name, p.main_name) main_name,
      coalesce(c.last_name, p.last_name) last_name,
      coalesce(c.strap_line, p.strap_line) strap_line,
      coalesce(c.thumb_storage, p.thumb_storage) image_storage,
      coalesce(c.profile_type, p.profile_type) profile_type,
      p.profile_status,
      p.profile_status_message,
      c.v
    from contacts c
    join users p on c.profile_user = p.id
    where :where
    order by coalesce(c.main_name, p.main_name)
    limit 50
    offset :offset
    """
    pages_sql = 'select (count(*) - 1) / 50 + 1 pages from contacts c where :where'

    async def call(self):
        # can't currently use raw sql here due to signing download urls
        where, offset = V('c.owner') == self.session.user_id, get_offset(self.request, paginate_by=50)
        return json_response(
            pages=await self.conn.fetchval_b(self.pages_sql, where=where),
            items=await self.get_items(where=where, offset=offset),
        )

    @listify
    async def get_items(self, where, offset):
        for r in await self.conn.fetch_b(self.items_sql, where=where, offset=offset):
            yield set_image_url(r, self.settings)


class ContactDetails(View):
    sql = """
    select
      c.id,
      c.profile_user user_id,
      p.email,

      c.profile_type c_profile_type,
      c.main_name c_main_name,
      c.last_name c_last_name,
      c.strap_line c_strap_line,
      c.image_storage c_image_storage,
      c.details c_details,
      c.v,

      p.visibility p_visibility,
      p.profile_type p_profile_type,
      p.main_name p_main_name,
      p.last_name p_last_name,
      p.strap_line p_strap_line,
      p.image_storage p_image_storage,
      p.profile_details p_details,
      p.profile_status,
      p.profile_status_message
    from contacts c
    join users p on c.profile_user = p.id
    where c.owner=$1 and c.id=$2
    """

    async def call(self):
        r = await self.conn.fetchrow(self.sql, self.session.user_id, int(self.request.match_info['id']))
        contact = {k: v for k, v in r.items() if v is not None and not k.endswith('image_storage') and k != 'v'}
        s3 = S3(self.settings)
        for prefix in ('c_', 'p_'):
            storage = r[prefix + 'image_storage']
            if storage:
                _, bucket, path = parse_storage_uri(storage)
                contact[prefix + 'image_url'] = s3.signed_download_url(bucket, path, version=r['v'])

        return json_response(**contact)


class ContactModel(BaseModel):
    email: EmailStr
    profile_type: Literal['personal', 'work', 'organisation'] = 'personal'
    main_name: constr(max_length=63) = None
    last_name: constr(max_length=63) = None
    strap_line: constr(max_length=127) = None
    details: constr(max_length=2000) = None
    image: UUID = None

    @validator('last_name')
    def clear_last_name_organisation(cls, v, values):
        if values.get('profile_type') == 'organisation':
            return None
        return v


class ContactCreateEdit(ExecView):
    Model = ContactModel

    async def get_create_user(self, email: str) -> int:
        user_id = await self.conns.main.fetchval(
            'insert into users (email) values ($1) on conflict (email) do nothing returning id', email
        )
        if not user_id:
            # email address already exists
            user_id = await self.conns.main.fetchval('select id from users where email=$1', email)
        return user_id

    async def get_image_data(self, s3_client: S3Client, image: UUID) -> Optional[Tuple[bytes, bytes]]:
        s: Settings = self.settings
        if not all((s.aws_secret_key, s.aws_access_key, s.s3_file_bucket)):  # pragma: no cover
            raise HTTPNotImplemented(text="Storage keys not set, can't upload files")

        if not image:
            return None

        cache_key = tmp_image_cache_key(str(image))
        storage_path = await self.redis.get(cache_key)
        key_exists = await self.redis.delete(cache_key)
        if not key_exists:
            msg = 'image not found'
            raise JsonErrors.HTTPBadRequest(msg, details=[{'loc': ['image'], 'msg': msg}])

        _, bucket, path = parse_storage_uri(storage_path)
        body = await s3_client.download(bucket, path)
        await s3_client.delete(bucket, path)
        try:
            return await resize_image(body, s.image_sizes, s.image_thumbnail_sizes)
        except InvalidImage as e:
            raise JsonErrors.HTTPBadRequest(str(e), details=[{'loc': ['image'], 'msg': str(e)}])

    async def upload_images(
        self, images: Tuple[bytes, bytes], contact_id: int, s3_client: S3Client
    ) -> Optional[Tuple[str, str]]:
        image_data, thumbnail_data = images
        main_path, thumb_path = self.image_paths(contact_id)
        return await asyncio.gather(
            s3_client.upload(self.settings.s3_file_bucket, main_path, image_data, 'image/jpeg'),
            s3_client.upload(self.settings.s3_file_bucket, thumb_path, thumbnail_data, 'image/jpeg'),
        )

    def image_paths(self, contact_id: int) -> Tuple[str, str]:
        path = f'contacts/{self.session.user_id}/{contact_id}/'
        return path + 'main.jpg', path + 'thumb.jpg'


class ContactCreate(ContactCreateEdit):
    async def execute(self, contact: ContactModel):
        user_id = await self.get_create_user(contact.email)

        async with S3(self.settings) as s3_client:
            images = await self.get_image_data(s3_client, contact.image)

            contact_id = await self.conns.main.fetchval_b(
                """
                insert into contacts (:values__names) values :values
                on conflict (owner, profile_user) do nothing returning id
                """,
                values=Values(
                    owner=self.session.user_id, profile_user=user_id, **contact.dict(exclude={'email', 'image'})
                ),
            )
            if not contact_id:
                msg = 'you already have a contact with this email address'
                raise JsonErrors.HTTPConflict(msg, details=[{'loc': ['email'], 'msg': msg}])

            if images:
                image, thumb = await self.upload_images(images, contact_id, s3_client)
                await self.conns.main.execute(
                    'update contacts set image_storage=$1, thumb_storage=$2 where id=$3', image, thumb, contact_id
                )

        return dict(id=contact_id, status_=201)


class ContactEdit(ContactCreateEdit):
    get_sql = """
    select p.email, c.profile_type, c.main_name, c.last_name, c.strap_line, c.image_storage, c.details, c.v
    from contacts c
    join users p on c.owner = p.id
    where c.owner=$1 and c.id=$2
    """

    async def get(self):
        r = await self.conn.fetchrow(self.get_sql, self.session.user_id, int(self.request.match_info['id']))
        return json_response(**set_image_url(r, self.settings, field_name='image'))

    async def parse_request(self) -> ContactModel:
        return await parse_request_json_ignore_missing(self.request, self.Model)

    async def execute(self, contact: ContactModel):
        if not contact.__fields_set__:
            raise JsonErrors.HTTPBadRequest('no data provided')
        data = contact.dict(exclude_unset=True, exclude={'image'})
        contact_id = int(self.request.match_info['id'])

        email = data.pop('email', None)
        if email:
            data['profile_user'] = await self.get_create_user(email)

        if contact.image:
            async with S3(self.settings) as s3_client:
                images = await self.get_image_data(s3_client, contact.image)
                image, thumb = await self.upload_images(images, contact_id, s3_client)
            data.update(image_storage=image, thumb_storage=thumb, v=V('v') + V('1'))
        elif 'image' in contact.__fields_set__:
            await self.delete_images(contact_id)
            data.update(image_storage=None, thumb_storage=None, v=V('v') + V('1'))

        v = await self.conn.execute_b(
            'update contacts set :values where id=:id and owner=:owner',
            values=SetValues(**data),
            id=contact_id,
            owner=self.session.user_id,
        )
        if v != 'UPDATE 1':
            raise JsonErrors.HTTPNotFound('contact not found')

    async def delete_images(self, contact_id: int):
        main_path, thumb_path = self.image_paths(contact_id)
        async with S3(self.settings) as s3_client:
            await asyncio.gather(
                s3_client.delete(self.settings.s3_file_bucket, main_path),
                s3_client.delete(self.settings.s3_file_bucket, thumb_path),
            )


def tmp_image_cache_key(content_id: str) -> str:
    return f'image-upload-{content_id}'


class UploadImage(View):
    class QueryModel(BaseModel):
        filename: constr(max_length=100)
        content_type: str
        # default to 10 MB
        size: conint(le=10 * 1024 ** 2)

        @validator('content_type')
        def check_content_type(cls, v: str) -> str:
            assert v in image_extensions, 'Invalid image Content-Type'
            return v

    async def call(self):
        s: Settings = self.settings
        if not all((s.aws_secret_key, s.aws_access_key, s.s3_file_bucket)):  # pragma: no cover
            raise HTTPNotImplemented(text="Storage keys not set, can't upload files")

        m = parse_request_query(self.request, self.QueryModel)
        image_id = str(uuid4())

        d = S3(s).signed_upload_url(
            bucket=s.s3_file_bucket,
            path=f'contacts/temp/{self.session.user_id}/{image_id}/',
            filename=m.filename,
            content_type=m.content_type,
            content_disp=True,
            size=m.size,
        )
        storage_path = 's3://{}/{}'.format(s.s3_file_bucket, d['fields']['Key'])
        await self.redis.setex(tmp_image_cache_key(image_id), self.settings.upload_pending_ttl, storage_path)
        await self.redis.enqueue_job('delete_stale_image', image_id, _defer_by=self.settings.upload_pending_ttl)
        return json_response(file_id=image_id, **d)


async def delete_stale_image(ctx, image_id: str):
    """
    Delete an uploaded image if the cache key still exists.
    """
    cache_key = tmp_image_cache_key(image_id)
    storage_path = await ctx['redis'].get(cache_key)
    key_exists = await ctx['redis'].delete(cache_key)
    if key_exists:
        _, bucket, path = parse_storage_uri(storage_path)
        async with S3(ctx['settings']) as s3_client:
            await s3_client.delete(bucket, path)
        return 1
