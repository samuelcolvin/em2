import {statuses} from '../lib'
import {make_url} from '../lib/requests'
import {db, get_convs, unix_ms, window_call} from './utils'

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
    this._session = session || this._session
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

    if (data.actions) {
      await apply_actions(data)
    } else if (data.user_v !== this._session.user_v) {
      // local data is out of date, needs updating
      await get_convs()
    } else {
      // just connecting, nothing has changed
      return
    }

    const session_update = {user_v: data.user_v}
    await db.sessions.update(this._session.session_id, session_update)
    Object.assign(this._session, session_update)
  }
}

async function apply_actions (data) {
  const actions = data.actions.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))

  await db.actions.bulkPut(actions)
  const action = actions[actions.length - 1]
  const conv = await db.conversations.get(action.conv)
  if (conv) {
    if (actions.length !== 1) {
      throw Error(`apply_actions assumes only one action if conversation already exists ${actions.length}`)
    }
    let prts = conv.details.prts
    prts += action.act === 'participants:add' ? 1: 0
    prts -= action.act === 'participants:remove' ? 1: 0
    let msgs = conv.details.msgs
    msgs += action.act === 'message:add' ? 1: 0
    msgs -= action.act === 'message:delete' ? 1: 0
    await db.conversations.update(action.conv, {
      updated_ts: action.ts,
      last_action_id: action.id,
      details: {
        act: action.act,
        sub: ['conv:publish', 'conv:create', 'subject:modify'].includes(action.act) ? action.body : conv.details.sub,
        email: action.actor,
        body: ['message:add', 'message:modify'].includes(action.act) ? action.body : conv.details.body,
        prts: prts,
        msgs: msgs,
      },
    })
  } else {
    await db.conversations.add({
      key: action.conv,
      created_ts: actions[0].ts,
      updated_ts: action.ts,
      last_action_id: action.id,
      published: Boolean(actions.find(a => a.act === 'conv:publish')),
      details: {
        act: action.act,
        sub: actions.find(a => ['conv:publish', 'conv:create', 'subject:modify'].includes(a.act)).body,
        email: action.actor,
        body: actions.find(a => ['message:add', 'message:modify'].includes(a.act)).body,
        prts: (
            actions.filter(a => a.act === 'participants:add').length -
            actions.filter(a => a.act === 'participants:remove').length
        ),
        msgs: (
            actions.filter(a => a.act === 'message:add').length -
            actions.filter(a => a.act === 'message:delete').length
        ),
      },
    })
  }
  window_call('change')
}

