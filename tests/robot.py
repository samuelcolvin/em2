#!/usr/bin/env python3
"""
Robot user of em2 that connects and does common stuff.
"""
import asyncio
import json
import sys
from datetime import datetime
from random import choice, random

import devtools
import lorem
from aiohttp import ClientSession, ClientTimeout

from em2.main import create_app
from em2.utils.web import MakeUrl

host = 'localhost:8000'
email = 'robot@example.com'
password = 'testing'

other_users = ['testing@example.com']


class Client:
    def __init__(self, session: ClientSession, main_app):
        self.session = session
        self._make_path = MakeUrl(main_app)
        self.convs = []

    async def run(self):
        await self.get_convs()
        while True:
            if random() > 0.8:
                await self.create()
            else:
                await self.act()
            await asyncio.sleep(random() * 3 + 2)

    async def login(self):
        print('logging in...')
        h = {'Origin': 'null', 'Referer': None}
        data = await self._post_json('auth:login', email=email, password=password, headers_=h)
        await self._post_json('ui:auth-token', auth_token=data['auth_token'])

    async def get_convs(self):
        print('getting convs...')
        data = await self._get('ui:list')
        # TODO paginate and get all convs once implemented
        self.convs = [c['key'] for c in data['conversations']]
        print(f'got {len(self.convs)} conversations')

    async def act(self):
        if not self.convs:
            await self.create()
            return
        conv_key = choice(self.convs)
        print(f'acting on {conv_key:.8}...')
        # TODO, choose between different actions
        await self._post_json(
            self._make_url('ui:act', conv=conv_key),
            act='message:add',
            body=f'New message at {datetime.now():%H:%M:%S}.\n\n{lorem.paragraph()}',
        )

    async def create(self):
        print('creating a conv...')
        publish = choice([True, False])
        data = await self._post_json(
            self._make_url('ui:create'),
            subject=lorem.sentence(),
            message=f'New conversation at {datetime.now():%H:%M:%S}.\n\n{lorem.paragraph()}',
            participants=other_users,
            publish=publish,
        )
        key = data['key']
        self.convs.append(key)
        print(f'new conv: {key:.8}..., published: {publish}, total: {len(self.convs)}')

    async def _get(self, view_name):
        url = self._make_url(view_name)
        async with self.session.get(url) as r:
            if r.status not in {200, 201}:
                try:
                    data = await r.json()
                except ValueError:
                    data = await r.text()
                devtools.debug(url, r.status, dict(r.headers), data)
                raise RuntimeError(f'unexpected response {r.status}')
            return await r.json()

    async def _post_json(self, view_name, *, headers_=None, **data):
        # TODO origin will need to be fixed for non local host usage
        headers = {
            'Content-Type': 'application/json',
            'Origin': 'http://localhost:3000',
            'Referer': 'http://localhost:3000/testing.js',
        }
        if headers_:
            headers.update(headers_)
        headers = {k: v for k, v in headers.items() if v is not None}

        url = self._make_url(view_name)
        data = json.dumps(data)
        async with self.session.post(url, data=data, headers=headers) as r:
            if r.status not in {200, 201}:
                try:
                    data = await r.json()
                except ValueError:
                    data = await r.text()
                devtools.debug(url, data, headers, r.status, dict(r.headers), data)
                raise RuntimeError(f'unexpected response {r.status}')
            return await r.json()

    def _make_url(self, view_name, *, query=None, **kwargs):
        if view_name.startswith('http'):
            return view_name
        assert not host.endswith('/'), f'host must not end with "/": "{host}"'

        path = self._make_path(view_name, query=query, **kwargs)
        app = view_name.split(':', 1)[0]

        if 'localhost' in host:
            return f'http://{host}{path}'
        else:
            return f'https://{app}.{host}{path}'


async def main():
    main_app = await create_app()
    async with ClientSession(timeout=ClientTimeout(total=5)) as session:
        client = Client(session, main_app)
        await client.login()
        if 'act' in sys.argv:
            await client.act()
        elif 'create' in sys.argv:
            await client.create()
        else:
            await client.run()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print('stopping')
