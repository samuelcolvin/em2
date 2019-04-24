import {sleep} from 'reactstrap-toolbox'
import {request as basic_request} from 'reactstrap-toolbox'
import {make_url, statuses} from '../utils/network'
import db from './worker_db'

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
      const error = {message: `method "${message.data.method}" not found`}
      postMessage({error, async_id: message.data.async_id})
    }
  } else {
    // console.log('worker running:', message.data.method, message.data.call_args || '')
    let result = method(message.data.call_args)

    const on_error = err => {
      console.warn(`worker error on ${message.data.method}:`, err, message)
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

async function request (method, app_name, path, config) {
  // wraps basic_request and re-authenticates when a session has expired, also takes care of allow_fail
  const url = make_url(app_name, path)
  try {
    return await basic_request(method, url, config)
  } catch (e) {
    if (e.status === 401) {
      // TODO check and reauthenticate
      // window_call here to update status
      await db.sessions.toCollection().delete()
    }
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

export let CONN_STATUS = null

export const set_conn_status = conn_status => {
  CONN_STATUS = conn_status
  window_call('setState', {conn_status})
}

export async function get_conn_status () {
  for (let i = 0; i < 20; i++) {
    if (![null, statuses.connecting].includes(CONN_STATUS)) {
      return CONN_STATUS
    }
    await sleep(50)
  }
  return CONN_STATUS
}

export const unix_ms = s => (new Date(s)).getTime()
