import debounce from 'debounce-async'
import {request as basic_request, conn_status} from '../lib/requests'
import {add_listener} from './utils'
import db from './db'

async function request (method, app_name, path, config) {
  // wraps basic_request and re-authenticates when a session has expired, also takes care of allow_fail
  try {
    return await basic_request(method, app_name, path, config)
  } catch (e) {
    if (e.status === 401) {
      // TODO check and reauthenticate
      await db.sessions.toCollection().delete()
    }
    if (config.allow_fail) {
      if (e.status === 0) {
        return conn_status.not_connected
      } else if (e.status === 401) {
        return conn_status.unauthorised
      }
    }
    throw e
  }
}

const requests = {
  get: (app_name, path, config) => request('GET', app_name, path, config),
  post: (app_name, path, data, config) => {
    config = config || {}
    config.send_data = data
    return request('POST', app_name, path, config)
  },
}

const get_session = () => db.sessions.toCollection().first()

add_listener('authenticate', async () => {
  return await get_session()
})

add_listener('list-conversations', async data => {
  const session = await get_session()
  if (!session) {
    return conn_status.unauthorised
  }
  const r = await requests.get('ui', '/list/', {allow_fail: true, args: {page: data.page}})
  if (conn_status[r]) {
    return r
  }
  return {items: r.data}
})

add_listener('auth-token', async data => {
  await requests.post('ui', '/auth-token/', {auth_token: data.auth_token})
  delete data.session.ts
  await db.sessions.put(data.session)
  return {address: data.session.address, name: data.session.name}
})

add_listener('create-conversation', async data => {
  console.log('worker, conv data:', data)
  return {status: 200}
})


const request_contacts = debounce(
  data => requests.get('ui', '/contacts/lookup-address/', {args: data}),
  1000
)

add_listener('contacts-lookup-address', async data => {
  const r = await request_contacts(data)
  console.log()
  return r.data
})
