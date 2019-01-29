import {DetailedError} from './index'

const request_domain = process.env.REACT_APP_DOMAIN

export function make_url (path, app_name) {
  if (!app_name) {
    return path
  } else {
    if (!path.startsWith('/')) {
      throw Error('path must start with "/"')
    } else if (app_name !== 'ui' && app_name !== 'auth') {
      throw Error('app_name must be "ui" or "auth"')
    }

    if (request_domain === 'localhost') {
      return `http://localhost:8000/${app_name}${path}`
    } else {
      return `https://${app_name}.${request_domain}${path}`
    }
  }
}

export function build_query (args) {
  const arg_list = []
  const add_arg = (n, v) => arg_list.push(encodeURIComponent(n) + '=' + encodeURIComponent(v))
  for (let [name, value] of Object.entries(args)) {
    if (Array.isArray(value)) {
      for (let value_ of value) {
        add_arg(name, value_)
      }
    } else if (value !== null && value !== undefined) {
      add_arg(name, value)
    }
  }
  if (arg_list.length > 0) {
    return '?' + arg_list.join('&')
  }
  return ''
}

function headers2obj (r) {
  const h = r.headers
  const entries = Array.from(h.entries())
  if (entries.length !== 0) {
    return Object.assign(...Array.from(h.entries()).map(([k, v]) => ({[k]: v})))
  }
}

export const UNAUTHORISED = '__unauthorised__'

export async function request (method, app_name, path, config) {
  let url = make_url(path, app_name)

  config = config || {}
  if (config.args) {
    url += build_query(config.args)
  }

  if (Number.isInteger(config.expected_status)) {
    config.expected_status = [config.expected_status]
  } else {
    config.expected_status = config.expected_status || [200]
  }

  const headers = {'Accept': 'application/json'}
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json'
  }

  const init = {method: method, headers: headers, credentials: 'include'}
  if (config.send_data) {
    init.body = JSON.stringify(config.send_data)
  }
  let r
  try {
    r = await fetch(url, init)
  } catch (error) {
    throw new DetailedError(error.message, {error, url, init})
  }
  if (r.status === 401) {
    // special case, return UNAUTHORISED
    return UNAUTHORISED
  } else if (config.expected_status.includes(r.status)) {
    return {
      data: await r.json(),
      status: r.status
    }
  } else {
    let response_data = {}
    try {
      response_data = await r.json()
    } catch (e) {
      // ignore and use normal error
    }
    const message = response_data.message || `Unexpected response ${r.status}`
    throw new DetailedError(message, {status: r.status, url, init, response_data, headers: headers2obj(r)})
  }
}


export default {
  get: (app_name, path, config) => request('GET', app_name, path, config),
  post: (app_name, path, data, config) => {
    config = config || {}
    config.send_data = data
    return request('POST', app_name, path, config)
  }
}
