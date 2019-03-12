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

worker_conversations()
worker_contacts()

add_listener('auth-token', async data => {
  await requests.post('ui', '/auth-token/', {auth_token: data.auth_token})
  delete data.session.ts
  data.session.cache = new Set()
  await db.sessions.add(data.session)
  await ws.connect(data.session)
  return {email: data.session.email, name: data.session.name}
})


add_listener('start', async () => {
  const session = await get_session()
  if (session) {
    window_call('setState', {user: session})
    await ws.connect(session)
  } else {
    // no session, check the internet connection
    try {
      const url = make_url('ui', '/online/')
      console.log(`checking connection status at ${url}`)
      await fetch(url, {method: 'HEAD'})
    } catch (error) {
      // generally TypeError: failed to fetch
      set_conn_status(statuses.offline)
      return
    }
    set_conn_status(statuses.online)
  }
})
