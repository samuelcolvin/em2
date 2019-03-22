import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {get_session} from './worker_db'
import db from './worker_db'
import {add_listener, window_call, route_message, set_conn_status, requests} from './worker_utils'
import Websocket from './worker_ws'
import worker_conversations from './worker_conversations'
import worker_contacts from './worker_contacts'

onmessage = route_message // eslint-disable-line no-undef

const ws = new Websocket()
let session

worker_conversations()
worker_contacts()

add_listener('auth-token', async data => {
  await requests.post('ui', '/auth/token/', {auth_token: data.auth_token})
  delete data.session.ts
  session = data.session
  session.cache = new Set()
  await db.sessions.add(session)
  await ws.connect(session)
  return {email: data.session.email, name: data.session.name}
})

add_listener('logout', async () => {
  ws.close()
  await requests.post('ui', '/auth/logout/')
  await db.sessions.where({session_id: session.session_id}).delete()
  window_call('setState', {user: null})
})

add_listener('start', async () => {
  session = await get_session()
  if (session) {
    window_call('setState', {user: session})
    await ws.connect(session)
  } else {
    // no session, check the internet connection
    const url = make_url('ui', '/online/')
    try {
      await fetch(url, {method: 'HEAD'})
    } catch (error) {
      // generally TypeError: failed to fetch, also CSP if rules are messed up
      set_conn_status(statuses.offline)
      console.debug(`checking connection status at ${url}: offline`)
      return
    }
    console.debug(`checking connection status at ${url}: online`)
    set_conn_status(statuses.online)
  }
})
