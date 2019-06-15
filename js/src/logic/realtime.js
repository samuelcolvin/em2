import {unix_ms, bool_int} from './utils'
import Websocket from './ws'
import WebPush from './web_push'

const meta_action_types = new Set([
  'seen',
  'subject:release',
  'subject:lock',
  'message:lock',
  'message:release',
])

export default class RealTime {
  constructor (main) {
    this._main = main
    this._conn = null
  }

  close = () => {
    this._conn.close()
  }

  connect = async () => {
    const web_push = new WebPush(this)
    const web_push_successful = await web_push.connect()
    if (web_push_successful) {
      console.debug('using web push for notifications')
      this._conn = web_push
    } else {
      console.debug('falling back to websockets for notifications')
      this._conn = new Websocket(this)
      this._conn.connect()
    }
  }

  on_message = async data => {
    console.debug('realtime message:', data)
    let clear_cache = false
    if (data.actions) {
      await this._apply_actions(data)
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

  _apply_actions = async (data) => {
    // console.log('actions:', data)
    const actions = data.actions.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))

    await this._main.session.db.actions.bulkPut(actions)
    const action = actions[actions.length - 1]
    const conv = await this._main.session.db.conversations.get(action.conv)
    const publish_action = actions.find(a => a.act === 'conv:publish')

    const other_actor = Boolean(actions.find(a => a.actor !== this._main.session.current.email))
    const self_creator = data.conv_details.creator === this._main.session.current.email
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
      await this._main.session.db.conversations.update(action.conv, update)
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
      await this._main.session.db.conversations.add(conv_data)

      if (!conv_data.seen && !data.spam) {
        notify_details = data.conv_details
      }
      const old_conv = await this._main.session.db.conversations.get({new_key: action.conv})
      if (old_conv) {
        await this._main.session.db.conversations.delete(old_conv.key)
        this._main.fire('change', {conv: old_conv.key, new_key: action.conv})
      }
    }
    this._main.fire('change', {conv: action.conv})
    await this._main.session.update_cache(`conv-${action.conv}`)

    if (this._main.session.current.flags !== data.flags) {
      await this._main.session.update({flags: data.flags})
      this._main.fire('flag-change', this._main.conversations.counts())
    }

    if (notify_details) {
      // TODO better summary of action
      this._main.notify.notify({
        title: action.actor,
        message: notify_details.sub,
        link: `/${action.conv.substr(0, 10)}/`,
      })
    }
  }
}
