import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import db from './worker_db'
import {unix_ms, window_call, set_conn_status} from './worker_utils'

const offline = 0
const connecting = 1
const online = 2

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
      console.warn('ws already connected')
      return
    }
    this._session = session || this._session
    set_conn_status(statuses.connecting)
    this._state = connecting
    let ws_url = make_url('ui', '/ws/').replace('http', 'ws')

    try {
      this._socket = new WebSocket(ws_url)
    } catch (error) {
      console.error('ws connection error', error)
      this._state = offline
      set_conn_status(statuses.offline)
      return
    }

    this._socket.onopen = () => {
      console.log('websocket open')
      set_conn_status(statuses.online)
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
        set_conn_status(statuses.online)
        window_call('setState', {user: null})
      } else {
        console.log(`websocket closed, reconnecting in ${reconnect_in}ms`, e)
        setTimeout(this.connect, reconnect_in)
        setTimeout(() => this._state === offline && set_conn_status(statuses.offline), 3000)
      }
    }
    this._socket.onerror = e => {
      console.debug('websocket error:', e)
      set_conn_status(statuses.offline)
    }
    this._socket.onmessage = this._on_message
  }

  _on_message = async event => {
    set_conn_status(statuses.online)
    const data = JSON.parse(event.data)

    if (data.actions) {
      await apply_actions(data)
    } else if (data.user_v === this._session.user_v) {
      // just connecting and nothing has changed
      return
    }

    const session_update = {user_v: data.user_v}
    if (data.user_v - this._session.user_v !== 1) {
      // user_v has increased by more than one, we must have missed actions, everything could have changed
      session_update.cache = new Set()
    }
    await db.sessions.update(this._session.session_id, session_update)
    Object.assign(this._session, session_update)
  }
}

async function apply_actions (data) {
  const actions = data.actions.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))

  await db.actions.bulkPut(actions)
  const action = actions[actions.length - 1]
  const conv = await db.conversations.get(action.conv)
  const publish_action = actions.find(a => a.act === 'conv:publish')
  if (conv) {
    const update = {
      updated_ts: action.ts,
      publish_ts: conv.publish_ts,
      last_action_id: action.id,
      details: data.conv_details,
    }
    if (publish_action) {
      update.publish_ts = publish_action.ts
    }
    await db.conversations.update(action.conv, update)
  } else {
    await db.conversations.add({
      key: action.conv,
      created_ts: actions[0].ts,
      updated_ts: action.ts,
      publish_ts: publish_action ? publish_action.ts : null,
      last_action_id: action.id,
      details: data.conv_details,
    })
    const old_conv = await db.conversations.get({new_key: action.conv})
    if (old_conv) {
      await db.conversations.delete(old_conv.key)
      window_call('change', {conv: old_conv.key, new_key: action.conv})
    }
  }
  window_call('change', {conv: action.conv})
}

