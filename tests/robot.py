#!/usr/bin/env python3
"""
Robot user of em2 that connects and does common stuff.
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from random import choice, random

import devtools
import lorem
from aiohttp import ClientSession, ClientTimeout, CookieJar

THIS_DIR = Path(__file__).parent.resolve()
sys.path.append(str(THIS_DIR.parent))

from em2.main import create_app  # noqa: E402
from em2.utils.web import MakeUrl  # noqa: E402

host = 'localhost:8000'
email = 'robot@example.com'
password = 'testing'

other_users = [{'email': 'testing@example.com'}, {'email': 'different@remote.com'}]


class Client:
    def __init__(self, session: ClientSession, main_app):
        self.session = session
        self._make_path = MakeUrl(main_app)
        self.convs = []

    async def run(self):
        while True:
            if random() > 0.5:
                await self.create()
            else:
                await self.act()
            await asyncio.sleep(random() * 3 + 2)

    async def login(self):
        print('logging in...')
        h = {'Origin': 'null', 'Referer': None}
        data = await self._post_json('auth:login', email=email, password=password, headers_=h)
        await self._post_json('ui:auth-token', auth_token=data['auth_token'])

    async def act(self, *, newest=False, seen=None):
        if not self.convs:
            await self.get_convs()
            if not self.convs:
                print('no conversations')
                await self.create()
                return

        if newest:
            conv_key = self.convs[-1]
        else:
            conv_key = choice(self.convs)
        print(f'acting on {conv_key:.10}...')

        if seen is None:
            seen = random() > 0.8

        if seen:
            print(f'marking {conv_key:.10} as seen...')
            response = await self._post_json(self._make_url('ui:act', conv=conv_key), actions=[dict(act='seen')])
        else:
            msg_format, msg_body = self._msg_body()
            print(f'adding message to {conv_key:.10}, format: {msg_format}...')
            actions = [dict(act='message:add', msg_format=msg_format, body=msg_body)]
            response = await self._post_json(self._make_url('ui:act', conv=conv_key), actions=actions)
        devtools.debug(response)

    async def create(self, *, publish=None):
        print('creating a conv...')
        publish = choice([True, False]) if publish is None else publish
        msg_format, msg_body = self._msg_body()
        data = await self._post_json(
            self._make_url('ui:create'),
            subject=lorem.sentence(),
            message=msg_body,
            msg_format=msg_format,
            participants=other_users,
            publish=publish,
        )
        key = data['key']
        self.convs.append(key)
        print(f'new conv: {key:.10}..., format: {msg_format}, published: {publish}, total: {len(self.convs)}')

    def _msg_body(self):
        html_path = THIS_DIR / 'email.html'
        msg_format = 'markdown'
        msg_body = f'New message at {datetime.now():%H:%M:%S}.\n\n{lorem.paragraph()}'
        if html_path.exists():
            if 'html' in sys.argv or random() > 0.5:
                msg_format = 'html'
                msg_body = html_path.read_text()
        else:
            print(f'email html not found at "{html_path}", forced to use markdown message')
        return msg_format, msg_body

    async def get_convs(self):
        print('getting convs...')
        data = await self._get('ui:list')
        # TODO paginate and get all convs once implemented
        self.convs = [c['key'] for c in data['conversations']]

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

    async def _post_json(self, view_name, *, headers_=None, **request_data):
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
        async with self.session.post(url, data=json.dumps(request_data), headers=headers) as r:
            if r.status not in {200, 201}:
                try:
                    data = await r.json()
                except ValueError:
                    data = await r.text()
                devtools.debug(url, request_data, headers, r.status, dict(r.headers), data)
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
    cookie_path = Path(__file__).parent.resolve() / './robot_cookies.pkl'
    cookies = CookieJar()
    if cookie_path.exists():
        cookies.load(cookie_path)
    async with ClientSession(timeout=ClientTimeout(total=5), cookie_jar=cookies) as session:
        try:
            client = Client(session, main_app)
            if not cookie_path.exists():
                await client.login()
            if 'act' in sys.argv:
                await client.act(newest=True)
            elif 'seen' in sys.argv:
                await client.act(newest=True, seen=True)
            elif 'message' in sys.argv:
                await client.act(newest=True, seen=False)
            elif 'create' in sys.argv:
                await client.create(publish=True)
            else:
                await client.run()
        finally:
            session.cookie_jar.save(cookie_path)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print('stopping')
