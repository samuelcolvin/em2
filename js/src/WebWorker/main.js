import debounce from 'debounce-async'
import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {add_listener, db, requests, window_call} from './utils'
import Websocket from './ws'

const conn_status = {
  unauthorised: 'unauthorised',
  not_connected: 'not_connected',
}

const ws = new Websocket()

const get_session = () => db.sessions.toCollection().first()

add_listener('list-conversations', async data => {
  // const r = await requests.get('ui', '/conv/list/', {allow_fail: true, args: {page: data.page}})
  // if (conn_status[r]) {
  //   return r
  // }
  // return {items: r.data}
  return {conversations: await db.conversations.orderBy('updated_ts').reverse().limit(50).toArray()}
})

add_listener('get-conversation', async data => {
  const session = await get_session()
  if (!session) {
    return conn_status.unauthorised
  }
  const r = await requests.get('ui', `/conv/${data.key}/`, {allow_fail: true})
  if (conn_status[r]) {
    return r
  }
  return {actions: r.data}
})

add_listener('auth-token', async data => {
  await requests.post('ui', '/auth-token/', {auth_token: data.auth_token})
  delete data.session.ts
  await db.sessions.put(data.session)
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
