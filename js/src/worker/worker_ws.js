import {sleep} from 'reactstrap-toolbox'
import {make_url, statuses} from '../utils/network'
import {session} from './worker_db'
import {unix_ms, window_call, set_conn_status, bool_int} from './worker_utils'

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
    if (!session) {
      console.warn('session null, not connecting to ws')
      return
    }
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

    let clear_cache = false
    if (data.actions) {
      await apply_actions(data)
      if (data.user_v - session.current.user_v !== 1) {
        // user_v has increased by more than one, we must have missed actions, everything could have changed
        clear_cache = true
      }
    } else if (data.user_v === session.current.user_v) {
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
    await session.update(session_update)
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

async function apply_actions (data) {
  console.log('actions:', data)
  const actions = data.actions.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))

  await session.db.actions.bulkPut(actions)
  const action = actions[actions.length - 1]
  const conv = await session.db.conversations.get(action.conv)
  const publish_action = actions.find(a => a.act === 'conv:publish')

  const other_actor = Boolean(actions.find(a => a.actor !== session.current.email))
  const self_creator = data.conv_details.creator === session.current.email
  const real_act = Boolean(actions.find(a => !meta_action_types.has(a.act)))
  let notify_details = null

  // FIXME all these counts might be wrong as we're assuming the conversation is actually new which it might not be
  const new_states = {}
  if (conv) {
    const update = {
      last_action_id: action.id,
      details: data.conv_details,
      spam: bool_int(data.spam),
      label_ids: data.label_ids || [],
    }
    const unseen = other_actor && real_act
    const now_unseen = unseen && conv.seen
    if (now_unseen) {
      update.seen = 0
    }
    if (unseen && !data.spam) {
      notify_details = conv.details
    }

    if (real_act) {
      update.updated_ts = action.ts
      if (data.spam && !conv.spam) {
        update.spam = bool_int(data.spam)
        new_states.spam = session.current.states.spam + 1
        if (now_unseen) {
          new_states.spam_unseen = session.current.states.spam_unseen + 1
        }
      } else {
        if (!conv.inbox) {
          update.inbox = 1
          new_states.inbox = session.current.states.inbox + 1
          if (now_unseen) {
            new_states.inbox_unseen = session.current.states.inbox_unseen + 1
          }
        }
        if (conv.deleted) {
          update.deleted = 0
          new_states.deleted = session.current.states.deleted - 1
        }
      }
    }
    if (publish_action && !conv.publish_ts) {
      update.publish_ts = publish_action.ts
      update.draft = 0
      update.sent = 1
      new_states.draft = session.current.states.draft - 1
      new_states.sent = session.current.states.sent + 1
    }
    await session.db.conversations.update(action.conv, update)
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
    await session.db.conversations.add(conv_data)

    if (conv_data.draft) {
      new_states.draft = session.current.states.draft + 1
    } else if (conv_data.inbox) {
      new_states.inbox = session.current.states.inbox + 1
      if (!conv_data.seen) {
        new_states.inbox_unseen = session.current.states.inbox_unseen + 1
      }
    } else if (conv_data.spam) {
      new_states.spam = session.current.states.spam + 1
      if (!conv_data.seen) {
        new_states.spam_unseen = session.current.states.spam_unseen + 1
      }
    }

    if (conv_data.sent) {
      new_states.sent = session.current.states.sent + 1
    }

    if (!conv_data.seen && !data.spam) {
      notify_details = data.conv_details
    }
    const old_conv = await session.db.conversations.get({new_key: action.conv})
    if (old_conv) {
      await session.db.conversations.delete(old_conv.key)
      window_call('change', {conv: old_conv.key, new_key: action.conv})
    }
  }
  window_call('change', {conv: action.conv})

  if (Object.keys(new_states).length) {
    await session.update({states: Object.assign({}, session.current.states, new_states)})
    window_call('states-change', await session.conv_counts())
  }

  if (notify_details) {
    // TODO better summary of action
    window_call('notify', {
      title: action.actor,
      message: notify_details.sub,
      link: `/${action.conv.substr(0, 10)}/`,
    })
  }
}
