import {sleep} from 'reactstrap-toolbox'
import {unix_ms, offset_limit, per_page, bool_int} from './utils'
import {statuses} from './network'


function actions_incomplete (actions) {
  // check we have all actions for a conversation, eg. ids are exactly incrementing
  let last_id = 0
  for (let a of actions) {
    if (a.id !== last_id + 1) {
      return last_id
    }
    last_id = a.id
  }
  return null
}


const _msg_action_types = new Set([
  'message:recover',
  'message:lock',
  'message:release',
  'message:add',
  'message:modify',
  'message:delete',
])
const _meta_action_types = new Set([
  'message:release',
  'subject:lock',
  'message:lock',
  'seen',
  'subject:release',
])


function warning_msgs (w) {
  if (!w) {
    return null
  }
  let warnings = Object.assign({}, w)
  const msgs = []
  if (warnings.spam) {
    msgs.push({
      title: 'Spam',
      message: {
        FAIL: 'Message appears to be spam',
        GRAY: 'Message may be spam',
        PROCESSING_FAILED: 'Unable to scan the message, may be be spam'
      }[warnings.spam] || `Message may be spam: ${warnings.spam}`
    })
    delete warnings.spam
  }
  if (warnings.virus) {
    msgs.push({
      title: 'Virus',
      message: {
        FAIL: "Message contains a virus",
        GRAY: 'unable to determine with confidence if the message contains a virus',
        PROCESSING_FAILED: 'Unable to scan the message for viruses'
      }[warnings.virus] || `Virus failed: ${warnings.virus}`
    })
    delete warnings.virus
  }
  if (warnings.dkim) {
    msgs.push({
      title: 'DKIM',
      message: {
        FAIL: "Message failed DKIM verification, this message may not be from who it says it's from",
        GRAY: 'Message not protected by DKIM',
        PROCESSING_FAILED: "Unable to check if the message's DKIM signature is valid"
      }[warnings.dkim] || `DKIM failed: ${warnings.dkim}`
    })
    delete warnings.dkim
  }
  if (warnings.spf) {
    msgs.push({
      title: 'SPF',
      message: {
        FAIL: "Message failed failed SPF authentication",
        GRAY: 'no SPF policy setup for the sending domain',
        PROCESSING_FAILED: "Unable to check if the message's SPF authentication is valid"
      }[warnings.spf] || `SPF failed: ${warnings.spf}`
    })
    delete warnings.spf
  }
  if (warnings.dmarc) {
    msgs.push({
      title: 'DMARC',
      message: {
        FAIL: "Message failed failed DMARC authentication",
        GRAY: 'Message failed DMARC authentication, and the sending domain does not have a DMARC policy',
        PROCESSING_FAILED: "Unable to check if the message's DMARC authentication is valid"
      }[warnings.dmarc] || `DMARC failed: ${warnings.dmarc}`
    })
    delete warnings.dmarc
  }
  for (let [title, value] of Object.entries(warnings)) {
    msgs.push({
      title,
      message: `unknown warning: ${value}`
    })
  }
  return msgs
}

// taken roughly from core.py:_construct_conv_actions
function construct_conv (conv, actions) {
  let subject = null
  let created = null
  const messages = {}
  const participants = {}

  for (let action of actions) {
    const act = action.act
    if (['conv:publish', 'conv:create'].includes(act)) {
      subject = action.body
      created = action.ts
    } else if (act === 'subject:modify') {
      subject = action.body
    } else if (act === 'message:add') {
      messages[action.id] = {
        first_action: action.id,
        last_action: action.id,
        body: action.body,
        creator: action.actor,
        created: action.ts,
        format: action.msg_format,
        parent: action.parent || null,
        active: true,
        files: action.files || null,
        comments: [],
        warnings: warning_msgs(action.warnings),
        hide_warnings: action.hide_warnings,
      }
    } else if (_msg_action_types.has(act)) {
      const message = messages[action.follows]
      message.last_action = action.id
      if (act === 'message:modify') {
        message.body = action.body
        message.editor = action.actor
      } else if (act === 'message:delete') {
        message.active = false
      } else if (act === 'message:recover') {
        message.active = true
      }
      messages[action.id] = message
    } else if (act === 'participant:add') {
      participants[action.participant] = {id: action.id}
    } else if (act === 'participant:remove') {
      delete participants[action.participant]
    } else if (!_meta_action_types.has(act)) {
      throw Error(`action "${act}" construction not implemented`)
    }
  }

  const msg_list = []
  for (let msg of Object.values(messages)) {
    let parent = msg.parent
    if (parent === undefined) {
      continue
    }
    delete msg.parent
    if (parent) {
      const parent_msg = messages[parent]
      parent_msg.comments.push(msg)
    } else {
      msg_list.push(msg)
    }
  }

  return {
    key: conv.key,
    draft: Boolean(conv.draft),
    sent: Boolean(conv.sent),
    inbox: Boolean(conv.inbox),
    archive: Boolean(conv.archive),
    deleted: Boolean(conv.deleted),
    spam: Boolean(conv.spam),
    seen: Boolean(conv.seen),
    primary_flag: primary_flag(conv),
    published: Boolean(actions.find(a => a.act === 'conv:publish')),
    subject: subject,
    created: created,
    messages: msg_list,
    participants,
    action_ids: new Set(actions.map(a => a.id)),
  }
}

const primary_flag = conv => {
  if (conv.deleted) {
    return 'deleted'
  } else if (conv.spam) {
    return 'spam'
  } else if (conv.inbox) {
    return 'inbox'
  } else if (conv.draft) {
    return 'draft'
  } else if (conv.sent) {
    return 'sent'
  } else {
    return 'archive'
  }
}

export default class Conversations {
  constructor (main) {
    this._main = main
    this._requests = this._main.requests
  }

  list = async (data) => {
    const flag = data.flag
    let status = await this._main.get_conn_status()
    if (!this._main.session.current) {
      return {}
    }
    if (status === statuses.online) {
      // have to get every page between 1 and the page requested to make sure the offset works correctly at the end
      for (let page = 1; page <= data.page; page ++) {
        const cache_key = `page-${flag}-${page}`
        if (!this._main.session.current.cache.has(cache_key)) {
          const r = await this._requests.get('ui', `/${this._main.session.id}/conv/list/`, {page, flag})
          const conversations = r.data.conversations.map(c => (
              Object.assign({}, c, {
                created_ts: unix_ms(c.created_ts),
                updated_ts: unix_ms(c.updated_ts),
                publish_ts: unix_ms(c.publish_ts),
                inbox: bool_int(c.inbox),
                draft: bool_int(c.draft),
                sent: bool_int(c.sent),
                archive: bool_int(c.archive),
                spam: bool_int(c.spam),
                deleted: bool_int(c.deleted),
              })
          ))
          await this._conv_table().bulkPut(conversations)
          this._main.session.current.cache.add(cache_key)
          await this._main.session.update({cache: this._main.session.current.cache})
      }
      }
    }
    const qs = this._conv_table().where({[flag]: 1})
    return offset_limit(await qs.reverse().sortBy('updated_ts'), data.page)
  }

  update_counts = async () => {
    let status = await this._main.get_conn_status()
    if (!this._main.session.current) {
      return {flags: {}, labels: []}
    }
    if (status === statuses.online && !this._main.session.current.cache.has('counts')) {
      const r = await this._requests.get('ui', `/${this._main.session.id}/conv/counts/`)

      this._main.session.current.cache.add('counts')
      await this._main.session.update({cache: this._main.session.current.cache, flags: r.data.flags})
      // TODO update labels, and return them
    }
    return this._main.session.conv_counts()
  }

  get_conversation = async key_prefix => {
    // TODO also need to look at the conversation and see if there are any new actions we've missed
    // TODO If the conversation doesn't exist, we need to get it from the server
    const conv = await this._get_conv(key_prefix)
    if (!conv) {
      return
    }
    let actions = await this._get_db_actions(conv.key)

    const last_action = actions_incomplete(actions)
    if (!actions.length || last_action !== null) {
      let url = `/${this._main.session.id}/conv/${conv.key}/`
      if (last_action) {
        url += `?since=${last_action}`
      }
      const r = await this._requests.get('ui', url)
      const new_actions = r.data.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))
      await this._main.session.db.actions.bulkPut(new_actions)
      actions = await this._get_db_actions(conv.key)
    }
    return construct_conv(conv, actions)
  }

  wait_for_conversation  = async key_prefix => {
    for (let i = 0; i < 50; i++) {
      let conv = await this._get_conv(key_prefix)
      if (conv) {
        return conv
      }
      await sleep(100)
    }
  }

  act = async (conv, actions) => {
    return await this._requests.post('ui', `/${this._main.session.id}/conv/${conv}/act/`, {actions: actions})
  }

  set_flag = async (conv_key, flag) => {
    const r = await this._requests.post(
      'ui',
      `/${this._main.session.id}/conv/${conv_key}/set-flag/`,
      {},
      {args: {flag}}
    )
    const update = {
      inbox: bool_int(r.data.conv_flags.inbox),
      unseen: bool_int(r.data.conv_flags.unseen),
      archive: bool_int(r.data.conv_flags.archive),
      deleted: bool_int(r.data.conv_flags.deleted),
      spam: bool_int(r.data.conv_flags.spam),
      draft: bool_int(r.data.conv_flags.draft),
      sent: bool_int(r.data.conv_flags.sent),
    }
    await this._conv_table().update(conv_key, update)
    this._main.fire('change', {conv: conv_key})

    if (this._main.session.current.flags !== r.data.counts) {
      await this._main.session.update({flags: r.data.counts})
      this._main.fire('flag-change', this._main.session.conv_counts())
    }
  }

  seen = async conv_key => {
    const conv = await this._conv_table().get(conv_key)
    if (!conv.seen) {
      await this._requests.post('ui', `/${this._main.session.id}/conv/${conv_key}/act/`, {actions: [{act: 'seen'}]})
    }
  }

  publish = async conv => {
    const r = await this._requests.post('ui', `/${this._main.session.id}/conv/${conv}/publish/`, {publish: true})
    await this._conv_table().update(conv, {new_key: r.data.key})
  }

  create = async data => (
    await this._requests.post('ui', `/${this._main.session.id}/conv/create/`, data, {expected_status: [201, 400]})
  )

  last_subject_action = async conv => {
    const acts = new Set(['conv:create', 'conv:publish', 'subject:lock', 'subject:release', 'subject:modify'])
    const actions = await (
      this._main.session.db.actions
      .where({conv: conv}).and(a => acts.has(a.act)).reverse().sortBy('id')
    )
    return actions[0].id
  }

  pages = flag => {
    const counts = this._main.session.conv_counts()
    return Math.ceil(counts.flags[flag] / per_page)
  }

  toggle_warnings = async (conv, action_id, show) => {
    // this is just saved locally, not on the server (for now?)
    await this._main.session.db.actions.update({conv, id: action_id}, {hide_warnings: show})
    this._main.fire('change', {conv})
  }

  _get_db_actions = conv => this._main.session.db.actions.where({conv}).sortBy('id')

  _get_conv = async key_prefix => {
    const convs = await this._conv_table().where('key').startsWith(key_prefix).reverse().sortBy('created_ts')
    return convs[0]
  }

  _conv_table = () => this._main.session.db.conversations
}
