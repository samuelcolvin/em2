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
  connecting: 'connecting',
  online: 'online',
}

export class Requests {
  constructor (main) {
    this._main = main
  }

  get = async (app_name, path, args, config={}) => (
    await this._request('GET', app_name, path, Object.assign({}, config, {args}))
  )

  post = async (app_name, path, send_data, config={}) => (
    await this._request('POST', app_name, path, Object.assign({}, config, {send_data}))
  )

  _request = async (method, app_name, path, config) => {
    const url = make_url(app_name, path)
    try {
      return await request(method, url, config)
    } catch (e) {
      if (e.status === 401) {
        // TODO check and reauthenticate
        await this._main.session.delete()
      }
      throw e
    }
  }
}
