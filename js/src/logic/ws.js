import {make_url, statuses} from './network'

export const meta_action_types = new Set([
  'seen',
  'subject:release',
  'subject:lock',
  'message:lock',
  'message:release',
])

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
    await this._realtime.on_message(data)
    if (should_notify(data)) {
      this._main.notify.notify({
        title: data.conv_details.sub,
        body: `${data.actions[0].actor}: ${data.conv_details.prev}`,
        data: {
          link: `/${data.actions[0].conv.substr(0, 10)}/`,
        },
        badge: '/android-chrome-192x192.png',  // image in notification bar
        icon: './android-chrome-512x512.png', // image next message in notification on android
      })
    }
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


function should_notify (data) {
  // duplicated from em2-service-worker.js
  if (!data.actions || !data.actions.some(a => a.actor !== data.user_email)) {
    // actions are all by "you"
    return false
  } else if (data.spam) {
    // conversation is spam
    return false
  } else {
    // otherwise check if there are any non-meta actions
    return data.actions.some(a => !meta_action_types.has(a.act))
  }
}
