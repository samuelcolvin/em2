import {sleep} from 'reactstrap-toolbox'
import {make_url, statuses} from '../utils/network'
import {session} from './worker_db'
import {unix_ms, window_call, set_conn_status} from './worker_utils'

const meta_action_types = new Set([
  'seen',
  'subject:release',
  'subject:lock',
  'message:lock',
  'message:release',
])
// reconnect after 50 seconds to avoid lots of 503 in heroku and also so we always have an active connection
const ws_ttl = 49900

export default class Websocket {
  constructor () {
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
    set_conn_status(statuses.connecting)
    this._socket = this._connect()
  }

  _connect = () => {
    let ws_url = make_url('ui', `/${session.id}/ws/`).replace('http', 'ws')
    let socket
    try {
      socket = new WebSocket(ws_url)
    } catch (error) {
      console.error('ws connection error', error)
      set_conn_status(statuses.offline)
      return null
    }

    socket.onopen = this._on_open
    socket.onclose = this._on_close
    socket.onerror = this._on_error
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

  _on_open = async () => {
    await sleep(100)
    if (this._socket) {
      console.debug('websocket open')
      set_conn_status(statuses.online)
      this._disconnects = 0
      window_call('notify-request')
      this._clear_reconnect = setTimeout(this._reconnect, ws_ttl)
    }
  }

  _on_message = async event => {
    set_conn_status(statuses.online)
    const data = JSON.parse(event.data)
    console.debug('ws message:', data)

    if (data.actions) {
      await apply_actions(data, session.current.email)
    } else if (data.user_v === session.current.user_v) {
      // just connecting and nothing has changed
      return
    }

    const session_update = {user_v: data.user_v}
    if (data.user_v - session.current.user_v !== 1) {
      // user_v has increased by more than one, we must have missed actions, everything could have changed
      session_update.cache = new Set()
    }
    await session.update(session_update)
  }

  _on_close = async e => {
    if (e.code === 1000 && e.target.manually_closing) {
      this._disconnects = 0
      console.debug('websocket closed intentionally')
      return
    }
    clearInterval(this._clear_reconnect)
    this._socket = null
    const reconnect_in = Math.min(20000, 2 ** this._disconnects * 500)
    this._disconnects += 1
    if (e.code === 4403) {
      console.debug('websocket closed with 4403, not authorised')
      set_conn_status(statuses.online)
      await session.delete()
      window_call('setState', {user: null})
      window_call('setState', {other_sessions: []})
    } else {
      console.debug(`websocket closed, reconnecting in ${reconnect_in}ms`, e)
      setTimeout(this.connect, reconnect_in)
      setTimeout(() => !this._socket && set_conn_status(statuses.offline), 3000)
    }
  }

  _on_error = () => {
    // console.debug('websocket error:', e)
    set_conn_status(statuses.offline)
    this._socket = null
  }
}

async function apply_actions (data, session_email) {
  const actions = data.actions.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))

  await session.db.actions.bulkPut(actions)
  const action = actions[actions.length - 1]
  const conv = await session.db.conversations.get(action.conv)
  const publish_action = actions.find(a => a.act === 'conv:publish')

  const other_actor = Boolean(actions.find(a => a.actor !== session_email))
  const real_act = Boolean(actions.find(a => !meta_action_types.has(a.act)))
  let notify_details = null
  if (conv) {
    const update = {
      last_action_id: action.id,
      details: data.conv_details,
    }
    if (real_act) {
      update.updated_ts = action.ts
    }
    if (publish_action) {
      update.publish_ts = publish_action.ts
    }
    if (other_actor && real_act) {
      update.seen = false
      notify_details = conv.details
    }
    await session.db.conversations.update(action.conv, update)
  } else {
    const unseen = other_actor && real_act
    await session.db.conversations.add({
      key: action.conv,
      created_ts: actions[0].ts,
      updated_ts: action.ts,
      publish_ts: publish_action ? publish_action.ts : null,
      last_action_id: action.id,
      details: data.conv_details,
      seen: !unseen,
    })
    if (unseen) {
      notify_details = data.conv_details
    }
    const old_conv = await session.db.conversations.get({new_key: action.conv})
    if (old_conv) {
      await session.db.conversations.delete(old_conv.key)
      window_call('change', {conv: old_conv.key, new_key: action.conv})
    }
  }
  window_call('change', {conv: action.conv})

  if (notify_details) {
    // TODO better summary of action
    window_call('notify', {
      title: action.actor,
      message: notify_details.sub,
      link: `/${action.conv.substr(0, 10)}/`,
    })
  }
}
