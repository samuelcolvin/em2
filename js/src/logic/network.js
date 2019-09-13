import {request} from 'reactstrap-toolbox'

export function make_url (app_name, path) {
  if (!path.startsWith('/')) {
    throw Error('path must start with "/"')
  } else if (app_name !== 'ui' && app_name !== 'auth') {
    throw Error('app_name must be "ui" or "auth"')
  } else if (process.env.REACT_APP_DOMAIN === 'localhost') {
    return `http://localhost:8000/${app_name}${path}`
  } else {
    return `https://${app_name}.${process.env.REACT_APP_DOMAIN}${path}`
  }
}

export const statuses = {
  offline: 'offline',
  problem: 'problem',
  connecting: 'connecting',
  online: 'online',
}

export class Requests {
  constructor (main) {
    this._main = main
  }

  get = async (app_name, path, args, config={}) => (
    await this._request('GET', app_name, path, {...config, args})
  )

  post = async (app_name, path, send_data, config={}) => (
    await this._request('POST', app_name, path, {...config, send_data})
  )

  _request = async (method, app_name, path, config) => {
    const url = make_url(app_name, path)
    let r
    try {
      r = await request(method, url, config)
    } catch (e) {
      console.debug(`networking: ${method} ${path} -> ${e.status}!`, e)
      if (e.status === 401) {
        await this._main.session.expired()
      } else if (!e.status || e.status > 501) {
        this._main.set_conn_status(statuses.problem)
      } else {
        this._main.fire('setError', e)
      }
      throw e
    }
    console.debug(`networking: ${method} ${path} -> ${r.status}`, r.data)
    this._main.set_conn_status(statuses.online)
    record_session_active()
    return r
  }
}

async function request_version () {
  try {
    const r = await fetch(`/version.txt?v=${Math.round(new Date().getTime() / 1000)}`)
    const text = await r.text()
    return text.replace('\n', '')
  } catch (error) {
    // generally TypeError: failed to fetch, also CSP if rules are messed up
    console.debug('offline, error:', error)
    return null
  }
}

export function get_version () {
  const timeout = new Promise(resolve => setTimeout(() => resolve(null), 1000))
  return Promise.race([request_version(), timeout])
}

const t = () => Math.round((new Date()).getTime() / 1000)

function record_session_active () {
  // TODO move this to the session object
  localStorage['session-last-active'] = t()
}

export const since_session_active = () => t() - parseInt(localStorage['session-last-active'])
