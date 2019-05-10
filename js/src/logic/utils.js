import {request as basic_request} from 'reactstrap-toolbox'
import {make_url} from '../utils/network'

async function request (method, app_name, path, config) {
  // wraps basic_request and re-authenticates when a session has expired, also takes care of allow_fail
  const url = make_url(app_name, path)
  try {
    return await basic_request(method, url, config)
  } catch (e) {
    if (e.status === 401) {
      // TODO check and reauthenticate
      // TODO fire here to update status, deleted session
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

export const unix_ms = s => (new Date(s)).getTime()

export const per_page = 50  // list pagination

export function offset_limit (arr, page) {
  const offset = (page - 1) * per_page
  return arr.slice(offset, offset + per_page)
}

export const bool_int = bool => bool ? 1: 0
