import db, {get_session} from './worker_db'
import {add_listener, get_conn_status, requests, unix_ms} from './worker_utils'
import {statuses} from '../lib'


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

const get_db_actions = conv_key => db.actions.where('conv').startsWith(conv_key).sortBy('id')

const _msg_action_types = [
    'message:recover', 'message:lock', 'message:release', 'message:add', 'message:modify', 'message:delete',
]

// taken roughly from core.py:_construct_conv_actions
function construct_conv (actions) {
  let subject = null
  let created = null
  const messages = {}
  const participants = {}

  for (let action of actions) {
    const act = action.act
    if (['conv:publish', 'conv:create'].includes(act)) {
      subject = action.body
      created = action.ts
    } else if (act === 'subject:lock') {
      subject = action.body
    } else if (act === 'message:add') {
      messages[action.id] = {
        'first_action': action.id,
        'last_action': action.id,
        'body': action.body,
        'creator': action.actor,
        'created': action.ts,
        'format': action.msg_format,
        'parent': action.parent || null,
        'active': true,
        'comments': [],
      }
    } else if (_msg_action_types.includes(act)) {
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
    } else if (act === 'seen') {
      // do nothing so far
    } else {
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
    // actions: actions,
    key: actions[0].conv,
    published: Boolean(actions.find(a => a.act === 'conv:publish')),
    subject: subject,
    created: created,
    messages: msg_list,
    participants: participants,
    action_ids: new Set(actions.map(a => a.id)),
  }
}

async function get_conversation (data) {
  // TODO also need to look at the conversation and see if there are any new actions we've missed
  let actions = await get_db_actions(data.key)

  const last_action = actions_incomplete(actions)
  if (!actions.length || last_action !== null) {
    let url = `/conv/${data.key}/`
    if (last_action) {
      url += `?since=${last_action}`
    }
    const r = await requests.get('ui', url)
    const new_actions = r.data.map(c => Object.assign(c, {ts: unix_ms(c.ts)}))
    await db.actions.bulkPut(new_actions)
    actions = await get_db_actions(data.key)
  }
  return construct_conv(actions)
}

const P = 50  // list pagination

async function list_conversations (data) {
  const page = data.page
  const status = await get_conn_status()
  if (status === statuses.online) {
    const session = await get_session()
    const cache_key = `page-${data.page}`
    if (!session.cache.has(cache_key)) {
      const r = await requests.get('ui', '/conv/list/', {args: {page}})
      const conversations = r.data.conversations.map(c => (
          Object.assign({}, c, {
            created_ts: unix_ms(c.created_ts),
            updated_ts: unix_ms(c.updated_ts),
            publish_ts: unix_ms(c.publish_ts),
          })
      ))
      await db.conversations.bulkPut(conversations)
      session.cache.add(cache_key)
      await db.sessions.update(session.session_id, {cache: session.cache, conv_count: r.data.count})
    }
  }

  const count = await db.conversations.count()
  return {
    conversations: await db.conversations.orderBy('updated_ts').reverse().offset((page - 1) * P).limit(P).toArray(),
    pages: Math.ceil(count / P),
  }
}

export default function () {
  add_listener('list-conversations', list_conversations)

  add_listener('get-conversation', get_conversation)

  add_listener('act', async data => {
    return await requests.post('ui', `/conv/${data.conv}/act/`, {actions: data.actions})
  })

  add_listener('publish', async data => {
    const r = await requests.post('ui', `/conv/${data.conv}/publish/`, {publish: true})
    await db.conversations.update(data.conv, {new_key: r.data.key})
  })

  add_listener('create-conversation', async data => {
    return await requests.post('ui', '/conv/create/', data, {expected_status: [201, 400]})
  })
}
