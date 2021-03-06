import {unix_ms, bool_int} from './utils'
import Websocket, {meta_action_types} from './ws'
import WebPush from './web_push'

export default class RealTime {
  constructor (main) {
    this._main = main
    this._conn = null
  }

  close = () => {
    this._conn.close()
  }

  connect = async () => {
    if (!this._main.auth.session_likely_active()) {
      // likely the session has expired, redirect to login without connecting to realtime
      await this._main.session.expired()
      return
    }
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
    // console.log('realtime message:', data)
    let clear_cache = false
    let events = []
    if (data.actions) {
      events = await this._apply_actions(data)
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
      if (!events.length) {
        events = [{channel: 'change'}]
      }
    }
    await this._main.session.update(session_update)
    for (let event of events) {
      this._main.fire(event.channel, event.details)
    }
  }

  _apply_actions = async (data) => {
    // console.log('actions:', data)
    const events = []
    const {interaction, conv_details} = data
    const conv_key = data.conversation
    const actions = data.actions.map(c => ({
      ...c,
      ts: unix_ms(c.ts),
      conv: conv_key,
      extra_body: bool_int(c.extra_body),
    }))

    await this._main.session.db.actions.bulkPut(actions)
    const last_action = actions[actions.length - 1]
    const conv_object = await this._main.session.db.conversations.get(conv_key)
    const publish_action = actions.find(a => a.act === 'conv:publish')

    const other_actor = actions.some(a => a.actor !== this._main.session.current.email)
    const self_creator = conv_details.creator === this._main.session.current.email
    const real_act = actions.some(a => !meta_action_types.has(a.act))

    if (conv_object) {
      const update = {
        last_action_id: last_action.id,
        details: conv_details,
        spam: bool_int(data.spam),
        label_ids: data.label_ids || [],
      }
      if (other_actor && real_act) {
        update.seen = 0
      } else if (!other_actor && last_action.act === 'seen') {
        update.seen = 1
      }

      if (real_act) {
        update.updated_ts = last_action.ts
        if (!update.spam) {
          update.inbox = 1
          update.deleted = 0
        }
      }
      if (publish_action && !conv_object.publish_ts) {
        update.publish_ts = publish_action.ts
        update.draft = 0
        update.sent = 1
      }
      await this._main.session.db.conversations.update(conv_key, update)
    } else {
      const conv_data = {
        key: conv_key,
        created_ts: actions[0].ts,
        updated_ts: last_action.ts,
        publish_ts: publish_action ? publish_action.ts : null,
        last_action_id: last_action.id,
        details: conv_details,
        sent: bool_int(self_creator && publish_action),
        draft: bool_int(self_creator && !publish_action),
        inbox: bool_int(!data.spam && other_actor),
        spam: bool_int(data.spam),
        seen: bool_int(!(other_actor && real_act)),
        label_ids: data.label_ids || [],
      }
      await this._main.session.db.conversations.add(conv_data)

      const old_conv = await this._main.session.db.conversations.get({new_key: conv_key})
      if (old_conv) {
        await this._main.session.db.conversations.delete(old_conv.key)
        events.push({channel: 'change', details: {conv: old_conv.key, new_key: conv_key, interaction}})
      }
    }
    events.push({channel: 'change', details: {conv: conv_key, interaction, last_action_id: last_action.id}})
    await this._main.session.update_cache(`conv-${conv_key}`)

    if (this._main.session.current.flags !== data.flags) {
      await this._main.session.update({flags: data.flags})
      events.push({channel: 'flag-change', details: this._main.conversations.counts()})
    }
    return events
  }
}
