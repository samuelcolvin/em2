import debounce from 'debounce-async'
import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {add_listener, db, requests, window_call} from './utils'
import Websocket from './ws'
import get_conversation from './get_conversation'

const ws = new Websocket()

const get_session = () => db.sessions.toCollection().first()

add_listener('list-conversations', async data => {
  // TODO if we're online and user_v has changed since the last get for this page (without being in sync), get
  // TODO use offset from data below
  return {conversations: await db.conversations.orderBy('updated_ts').reverse().limit(50).toArray()}
})

add_listener('get-conversation', get_conversation)

add_listener('act', async data => {
  console.log('act, conv data:', data)
  return await requests.post('ui', `/conv/${data.conv}/act/`, data.act)
})

add_listener('auth-token', async data => {
  await requests.post('ui', '/auth-token/', {auth_token: data.auth_token})
  delete data.session.ts
  await db.sessions.add(data.session)
  await ws.connect(data.session)
  return {email: data.session.email, name: data.session.name}
})

add_listener('create-conversation', async data => {
  console.log('worker, conv data:', data)
  return await requests.post('ui', '/conv/create/', data, {expected_status: [201, 400]})
})

const request_contacts = debounce(
  data => requests.get('ui', '/contacts/lookup-email/', {args: data}),
  1000
)

add_listener('contacts-lookup-email', async data => {
  const r = await request_contacts(data)
  return r.data
})

add_listener('start', async () => {
  const session = await get_session()
  if (session) {
    window_call('setState', {user: session})
    await ws.connect(session)
  } else {
    // no session, check the internet connection
    try {
      await fetch(make_url('ui', '/online/'), {method: 'HEAD'})
    } catch (error) {
      // generally TypeError: failed to fetch
      window_call('setState', {conn_status: statuses.offline})
      return
    }
    window_call('setState', {conn_status: statuses.online})
  }
})
