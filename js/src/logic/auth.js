import {since_session_active} from './network'

export default class Auth {
  constructor (main) {
    this._main = main
  }

  auth_token = async data => {
    const r = await this._main.requests.post('ui', '/auth/token/', {auth_token: data.auth_token})
    delete data.session.ts
    data.session.cache = new Set()
    data.session.user_id = r.data.user_id
    await this._main.session.new(data.session)
    return {email: data.session.email, name: data.session.name}
  }

  session_likely_active = () => parseInt(localStorage['session-last-active']) > since_session_active()

  logout = async () => {
    this._main.realtime.close()
    await this._main.requests.post('ui', `/${this._main.session.id}/auth/logout/`)
    await this._main.session.finish()
  }
}
