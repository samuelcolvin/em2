import debounce from 'debounce-async'
import isEmail from 'validator/lib/isEmail'
import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {add_listener, db, requests, window_call, get_conn_status, unix_ms} from './utils'
import Websocket from './ws'
import get_conversation from './get_conversation'

const ws = new Websocket()

const get_session = () => db.sessions.toCollection().first()
const P = 50  // list pagination

add_listener('list-conversations', async data => {
  const page = data.page
  const status = await get_conn_status()
  if (status === statuses.online) {
    const session = await get_session()
    const cache_key = `page-${data.page}`
    if (!session.cache.has(cache_key)) {
      const r = await requests.get('ui', '/conv/list/', {args: {page}})
      const conversations = r.data.conversations.map(c => (
          Object.assign({}, c, {
            created_ts: unix_ms(c.created_ts),
            updated_ts: unix_ms(c.updated_ts),
            publish_ts: unix_ms(c.publish_ts),
          })
      ))
      await db.conversations.bulkPut(conversations)
      session.cache.add(cache_key)
      await db.sessions.update(session.session_id, {cache: session.cache, conv_count: r.data.count})
    }
  }

  const count = await db.conversations.count()
  return {
    conversations: await db.conversations.orderBy('updated_ts').reverse().offset((page - 1) * P).limit(P).toArray(),
    pages: Math.ceil(count / P)
  }
})

add_listener('get-conversation', get_conversation)

add_listener('act', async data => {
  return await requests.post('ui', `/conv/${data.conv}/act/`, data.act)
})

add_listener('publish', async data => {
  const r = await requests.post('ui', `/conv/${data.conv}/publish/`, {publish: true})
  await db.conversations.update(data.conv, {new_key: r.data.key})
})

add_listener('auth-token', async data => {
  await requests.post('ui', '/auth-token/', {auth_token: data.auth_token})
  delete data.session.ts
  data.session.cache = new Set()
  await db.sessions.add(data.session)
  await ws.connect(data.session)
  return {email: data.session.email, name: data.session.name}
})

add_listener('create-conversation', async data => {
  return await requests.post('ui', '/conv/create/', data, {expected_status: [201, 400]})
})

add_listener('fast-email-lookup', async data => {
  let email = data.query
  let name = ''
  const m = email.match(/^ *([\w ]+?) *<(.+)> *$/)
  if (m) {
    name = m[1]
    email = m[2]
  }
  email = email.trim()
  // console.log([name, email], isEmail(email))
  if (!isEmail(email)) {
    return null
  }
  // TODO search for email addresses in indexeddb
  return [{name, email: email.toLowerCase()}]
})

const request_contacts = debounce(
  data => requests.get('ui', '/contacts/lookup-email/', {args: data}),
  300 // may have to increase this in future
)

add_listener('slow-email-lookup', async data => {
  try {
    const r = await request_contacts(data)
    console.log(r)
    return r.data
  } catch (e) {
    if (e === 'canceled') {
      return null
    } else {
      throw e
    }
  }
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
