import requests, {conn_status} from '../lib/requests'
import {add_listener, window_trigger} from './utils'
import db from './db'

add_listener('authenticate', async () => {
  return await db.sessions.toCollection().first()
})

add_listener('list-conversations', async data => {
  const r = await requests.get('ui', `/list/?page=${data.page}`, {allow_fail: true})
  if (conn_status[r]) {
    return r
  }
  return {items: r.data}
})

add_listener('auth-token', async data => {
  console.log('auth-token data:', data)
  await requests.post('ui', '/auth-token/', {auth_token: data.auth_token})
  delete data.session.ts
  await db.sessions.put(data.session)
  window_trigger('setUser', {address: data.session.address, name: data.session.name})
})
