import {sleep} from 'reactstrap-toolbox'
import {make_url, statuses} from '../utils/network'
import {unix_ms, bool_int} from './utils'

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
  constructor (main) {
    this._main = main
    this._sess = main.session
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
    this._main.set_conn_status(statuses.connecting)
    this._socket = this._connect()
  }

  _connect = () => {
    if (!this._sess) {
      console.warn('session null, not connecting to ws')
      return
    }
    let ws_url = make_url('ui', `/${this._sess.id}/ws/`).replace('http', 'ws')
    let socket
    try {
      socket = new WebSocket(ws_url)
    } catch (error) {
      console.error('ws connection error', error)
      this._main.set_conn_status(statuses.offline)
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
      this._main.set_conn_status(statuses.online)
      this._disconnects = 0
      this._main.fire('notify-request')
      this._clear_reconnect = setTimeout(this._reconnect, ws_ttl)
    }
  }

  _on_message = async event => {
    this._main.set_conn_status(statuses.online)
    const data = JSON.parse(event.data)
    console.debug('ws message:', data)

    let clear_cache = false
    if (data.actions) {
      await this._apply_actions(data)
      if (data.user_v - this._sess.current.user_v !== 1) {
        // user_v has increased by more than one, we must have missed actions, everything could have changed
        clear_cache = true
      }
    } else if (data.user_v === this._sess.current.user_v) {
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
    await this._sess.update(session_update)
  }

  _on_close = async e => {
    clearInterval(this._clear_reconnect)
    if (e.code === 1000 && e.target && e.target.manually_closing) {
      this._disconnects = 0
      console.debug('websocket closed intentionally')
      return
    }
    this._socket = null
    const reconnect_in = Math.min(20000, 2 ** this._disconnects * 500)
    this._disconnects += 1
    if (e.code === 4403) {
      console.debug('websocket closed with 4403, not authorised')
      this._main.set_conn_status(statuses.online)
      await this._sess.delete()
      this._main.fire('setState', {user: null})
      this._main.fire('setState', {other_sessions: []})
    } else {
      console.debug(`websocket closed, reconnecting in ${reconnect_in}ms`, e)
      setTimeout(this.connect, reconnect_in)
      setTimeout(() => !this._socket && this._main.set_conn_status(statuses.offline), 3000)
    }
  }

  _on_error = () => {
    // console.debug('websocket error:', e)
    this._main.set_conn_status(statuses.offline)
    this._socket = null
  }

  _apply_actions = async (data) => {
    // console.log('actions:', data)
    const actions = data.actions.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))

    await this._sess.db.actions.bulkPut(actions)
    const action = actions[actions.length - 1]
    const conv = await this._sess.db.conversations.get(action.conv)
    const publish_action = actions.find(a => a.act === 'conv:publish')

    const other_actor = Boolean(actions.find(a => a.actor !== this._sess.current.email))
    const self_creator = data.conv_details.creator === this._sess.current.email
    const real_act = Boolean(actions.find(a => !meta_action_types.has(a.act)))
    let notify_details = null

    if (conv) {
      const update = {
        last_action_id: action.id,
        details: data.conv_details,
        spam: bool_int(data.spam),
        label_ids: data.label_ids || [],
      }
      if (other_actor && real_act) {
        update.seen = 0
        if (!update.spam) {
          notify_details = conv.details
        }
      } else if (!other_actor && action.act === 'seen') {
        update.seen = 1
      }

      if (real_act) {
        update.updated_ts = action.ts
        if (!update.spam) {
          update.inbox = 1
          update.deleted = 0
        }
      }
      if (publish_action && !conv.publish_ts) {
        update.publish_ts = publish_action.ts
        update.draft = 0
        update.sent = 1
      }
      console.log('update:', update)
      await this._sess.db.conversations.update(action.conv, update)
    } else {
      const conv_data = {
        key: action.conv,
        created_ts: actions[0].ts,
        updated_ts: action.ts,
        publish_ts: publish_action ? publish_action.ts : null,
        last_action_id: action.id,
        details: data.conv_details,
        sent: bool_int(self_creator && publish_action),
        draft: bool_int(self_creator && !publish_action),
        inbox: bool_int(!data.spam && other_actor),
        spam: bool_int(data.spam),
        seen: bool_int(!(other_actor && real_act)),
        label_ids: data.label_ids || [],
      }
      await this._sess.db.conversations.add(conv_data)

      if (!conv_data.seen && !data.spam) {
        notify_details = data.conv_details
      }
      const old_conv = await this._sess.db.conversations.get({new_key: action.conv})
      if (old_conv) {
        await this._sess.db.conversations.delete(old_conv.key)
        this._main.fire('change', {conv: old_conv.key, new_key: action.conv})
      }
    }
    this._main.fire('change', {conv: action.conv})

    if (this._sess.current.flags !== data.flags) {
      await this._sess.update({flags: data.flags})
      this._main.fire('flag-change', await this._sess.conv_counts())
    }

    if (notify_details) {
      // TODO better summary of action
      this._main.fire('notify', {
        title: action.actor,
        message: notify_details.sub,
        link: `/${action.conv.substr(0, 10)}/`,
      })
    }
  }
}
