import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {get_session, other_sessions} from './worker_db'
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

const update_sessions = async session => {
  window_call('setUser', session)
  window_call('setState', {other_sessions: await other_sessions(session.session_id)})
  await ws.connect(session)
}

add_listener('auth-token', async data => {
  // TODO pass db.sessions.where({email: session.email}).toArray() so those sessions can be terminated.
  await requests.post('ui', '/auth/token/', {auth_token: data.auth_token})
  delete data.session.ts
  session = data.session
  session.cache = new Set()
  await db.sessions.where({email: session.email}).delete()
  await db.sessions.add(session)
  await update_sessions(session)
  return {email: data.session.email, name: data.session.name}
})

add_listener('logout', async () => {
  ws.close()
  await requests.post('ui', '/auth/logout/')
  console.log(session, await db.sessions.where({email: session.email}).toArray())
  await db.sessions.where({email: session.email}).delete()
  window_call('setUser', null)
})

add_listener('switch', async session_id => {
  console.log(session_id)
  session = await get_session(session_id)
  await update_sessions(session)
  return {email: session.email, name: session.name}
})

add_listener('start', async session_id => {
  session = await get_session(session_id)
  if (session) {
    await update_sessions(session)
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
