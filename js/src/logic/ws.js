import {make_url, statuses} from './network'

// reconnect after 50 seconds to avoid lots of 503 in heroku and also so we always have an active connection
const ws_ttl = 49900

export default class Websocket {
  constructor (realtime) {
    this._realtime = realtime
    this._main = realtime._main
    this._disconnects = 0
    this._socket = null
    this._clear_reconnect = null
  }

  close = () => {
    this._socket.manually_closing = true
    this._socket.close()
  }

  connect = () => {
    if (this._socket) {
      console.warn('ws already connected, not connecting again')
      return
    }
    this._socket = this._connect()
  }

  _connect = () => {
    if (!this._main.session.id) {
      console.warn('session null, not connecting to ws')
      return
    }
    let ws_url = make_url('ui', `/${this._main.session.id}/ws/`).replace(/^http/, 'ws')
    let socket
    try {
      socket = new WebSocket(ws_url)
    } catch (error) {
      console.error('ws connection error', error)
      this._main.set_conn_status(statuses.offline)
      return null
    }
    this._main.set_conn_status(statuses.connecting)

    socket.onclose = this._on_close
    socket.onerror = this._on_error
    this._first_msg = true
    socket.onmessage = this._on_message
    return socket
  }

  _reconnect = () => {
    const new_socket = this._connect()
    if (new_socket) {
      this.close()
      this._socket = new_socket
    }
  }

  _on_message = async event => {
    this._main.set_conn_status(statuses.online)
    if (this._first_msg) {
      console.debug('websocket open')
      this._disconnects = 0
      this._main.notify.request()
      this._clear_reconnect = setTimeout(this._reconnect, ws_ttl)
      this._first_msg = false
    }
    const data = JSON.parse(event.data)
    console.debug('ws message:', data)

    let clear_cache = false
    if (data.actions) {
      await this._realtime.apply_actions(data)
      if (data.user_v - this._main.session.current.user_v !== 1) {
        // user_v has increased by more than one, we must have missed actions, everything could have changed
        clear_cache = true
      }
    } else if (data.user_v === this._main.session.current.user_v) {
      // just connecting and nothing has changed
      return
    } else {
      // just connecting but user_v has increased, everything could have changed
      clear_cache = true
    }

    const session_update = {user_v: data.user_v}
    if (clear_cache) {
      session_update.cache = new Set()
    }
    await this._main.session.update(session_update)
  }

  _on_close = async e => {
    clearInterval(this._clear_reconnect)
    if (e.code === 1000 && e.target && e.target.manually_closing) {
      this._disconnects = 0
      console.debug('websocket closed intentionally')
      return
    }
    this._socket = null
    if (e.code === 4403) {
      console.debug('websocket closed with 4403, not authorised')
      this._main.set_conn_status(statuses.online)
      await this._main.session.expired()
      return
    } else if (e.code === 4401) {
      console.debug(`websocket closed, re-authenticating and reconnecting`, e)
      await this._main.requests.get('ui', `/${this._main.session.id}/auth/check/`)
      this.connect()
    } else {
      this._disconnects += 1
      const reconnect_in = Math.min(20000, 2 ** this._disconnects * 500)
      setTimeout(this.connect, reconnect_in)
      console.debug(`websocket closed, reconnecting in ${reconnect_in}ms`, e)
    }
    setTimeout(() => !this._socket && this._main.set_conn_status(statuses.offline), 3000)
  }

  _on_error = () => {
    // console.debug('websocket error:', e)
    this._main.set_conn_status(statuses.offline)
    this._socket = null
  }
}
