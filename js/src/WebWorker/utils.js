import Dexie from 'dexie'
import {request as basic_request} from '../lib/requests'

export function window_call (method, call_args) {
  postMessage({method, call_args})
}

export const LISTENERS = {}

export function add_listener (name, listener) {
  LISTENERS[name || listener.name] = listener
}

export function route_message (message) {
  const method = LISTENERS[message.data.method]
  if (method === undefined) {
    console.error(`worker: method "${message.data.method}" not found`)
    if (message.data.async_id) {
      postMessage({error: `method "${message.data.method}" not found`, async_id: message.data.async_id})
    }
  } else {
    // console.log('worker running:', message.data.method, message.data.call_args || '')
    let result = method(message.data.call_args)

    const on_error = err => {
      console.warn('worker error:', err)
      const error = {message: err.message || err.toString(), details: err.details}
      postMessage({error, async_id: message.data.async_id})
    }

    if (result.then) {
      result.then(
        result => postMessage({result, async_id: message.data.async_id}),
        err => on_error(err)
      )
    } else {
      try {
        postMessage({result, async_id: message.data.async_id})
      } catch (err) {
        on_error(err)
      }
    }
  }
}

export const db = new Dexie('em2')
db.version(1).stores({
  sessions: '&session_id, email',
  conversations: '&key, created_ts, updated_ts, published',
  actions: '[conv+id], [conv+act], conv, ts',
})

async function request (method, app_name, path, config) {
  // wraps basic_request and re-authenticates when a session has expired, also takes care of allow_fail
  try {
    return await basic_request(method, app_name, path, config)
  } catch (e) {
    if (e.status === 401) {
      // TODO check and reauthenticate
      // window_call here to update status
      await db.sessions.toCollection().delete()
    }
    // if (config.allow_fail) {
    //   if (e.status === 0) {
    //     return conn_status.not_connected
    //   } else if (e.status === 401) {
    //     return conn_status.unauthorised
    //   }
    // }
    throw e
  }
}

export const requests = {
  get: (app_name, path, config) => request('GET', app_name, path, config),
  post: (app_name, path, data, config) => {
    config = config || {}
    config.send_data = data
    return request('POST', app_name, path, config)
  },
}

export const unix_ms = s => (new Date(s)).getTime()

export async function get_convs (session, page = 1) {
  const r = await requests.get('ui', '/conv/list/', {args: {page}})
  const conversations = r.data.conversations.map(c => (
      Object.assign({}, c, {
        created_ts: unix_ms(c.created_ts),
        updated_ts: unix_ms(c.updated_ts),
      })
  ))
  await db.conversations.bulkPut(conversations)
  return {conversations, count: r.data.count}
}
