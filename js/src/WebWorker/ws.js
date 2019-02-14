import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {db, get_convs, window_call} from './utils'

const offline = 0
const connecting = 1
const online = 2

const window_conn_status = conn_status => window_call('setState', {conn_status})

export default class Websocket {
  constructor () {
    this._state = offline  // see above for options
    this._disconnects = 0
    this._socket = null
    this._session = null
    this.connect = this.connect.bind(this)
  }

  async connect (session) {
    if (this._state !== offline) {
      // console.log('ws already connected')
      return
    }
    this._session = session
    window_conn_status(statuses.connecting)
    this._state = connecting
    let ws_url = make_url('ui', '/ws/').replace('http', 'ws')

    try {
      this._socket = new WebSocket(ws_url)
    } catch (error) {
      console.error('ws connection error', error)
      this._state = offline
      window_conn_status(statuses.offline)
      return
    }

    this._socket.onopen = () => {
      console.log('websocket open')
      window_conn_status(statuses.online)
      this._state = online
      setTimeout(() => {
        if (this._state === online) {
          this._disconnects = 0
        }
      }, 500)
    }

    this._socket.onclose = e => {
      this._state = offline
      const reconnect_in = Math.min(10000, (2 ** this._disconnects - 1) * 500)
      this._disconnects += 1
      if (e.code === 4403) {
        console.log('websocket closed with 4403, not authorised')
        window_call('setState', {user: null, conn_status: statuses.online})
      } else {
        console.log(`websocket closed, reconnecting in ${reconnect_in}ms`, e)
        setTimeout(this.connect, reconnect_in)
        setTimeout(() => this._state === offline && window_conn_status(statuses.offline), 3000)
      }
    }
    this._socket.onerror = e => {
      console.debug('websocket error:', e)
      window_conn_status(statuses.offline)
    }
    this._socket.onmessage = this._on_message
  }

  _on_message = async event => {
    window_conn_status(statuses.online)
    const data = JSON.parse(event.data)

    if (data.user_v) {
      if (data.user_v !== this._session.user_v) {
        // local data is out of date, needs updating
        const r = await get_convs()
        const session_update = {user_v: data.user_v, conv_count: r.count}
        await db.sessions.update(this._session.session_id, session_update)
        Object.assign(this._session, session_update)
      }
    } else {
      console.log('ws message:', data)
      window_call('change')
    }
  }
}
