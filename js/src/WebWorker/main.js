import debounce from 'debounce-async'
import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {add_listener, db, requests, unix_ms, window_call} from './utils'
import Websocket from './ws'

const ws = new Websocket()

const get_session = () => db.sessions.toCollection().first()

add_listener('list-conversations', async data => {
  // TODO if we're online and user_v has changed since the last get for this page (without being in sync), get
  // TODO use offset from data below
  return {conversations: await db.conversations.orderBy('updated_ts').reverse().limit(50).toArray()}
})


const actions_incomplete = actions => {
  // check we have all actions for a conversation, eg. ids are exactly incrementing
  let last_id = 0
  for (let a of actions) {
    if (a.id !== last_id + 1) {
      return last_id
    }
    last_id = a.id
  }
  return null
}

const get_actions = conv_key => db.actions.where('conv').startsWith(conv_key).sortBy('id')

add_listener('get-conversation', async data => {
  let actions = await get_actions(data.key)

  const last_action = actions_incomplete(actions)
  if (last_action !== null) {
    const r = await requests.get('ui', `/conv/${data.key}/?since=${last_action}`)
    const new_actions = r.data.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))
    await db.actions.bulkPut(new_actions)
    actions = await get_actions(data.key)
  }
  return {actions}
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
