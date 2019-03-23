import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import db, {session} from './worker_db'
import {add_listener, window_call, route_message, set_conn_status, requests} from './worker_utils'
import Websocket from './worker_ws'
import worker_conversations from './worker_conversations'
import worker_contacts from './worker_contacts'

onmessage = route_message // eslint-disable-line no-undef

const ws = new Websocket()

worker_conversations()
worker_contacts()

const update_sessions = async () => {
  window_call('setUser', session.current)
  window_call('setState', {other_sessions: await session.others()})
  await ws.connect(session.current)
}

add_listener('auth-token', async data => {
  await requests.post('ui', '/auth/token/', {auth_token: data.auth_token})
  delete data.session.ts
  data.session.cache = new Set()
  await session.add(data.session)
  await update_sessions()
  return {email: data.session.email, name: data.session.name}
})

add_listener('logout', async () => {
  ws.close()
  await requests.post('ui', `/${session.id}/auth/logout/`)
  await db.sessions.where({session_id: session.id}).delete()
  window_call('setUser', null)
})

add_listener('switch', async session_id => {
  await session.update(session_id)
  await update_sessions()
  return {email: session.email, name: session.name}
})

add_listener('start', async session_id => {
  await session.update(session_id)
  if (session.id) {
    await update_sessions()
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
