import {db, requests, unix_ms} from './utils'


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
    subject: subject,
    created: created,
    messages: msg_list,
    participants: participants,
    action_ids: new Set(actions.map(a => a.id)),
  }
}

export default async function (data) {
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
