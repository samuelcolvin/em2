import debounce from 'debounce-async'
import isEmail from 'validator/lib/isEmail'
import {session} from './worker_db'
import {add_listener, requests} from './worker_utils'

function parse_address (email) {
  let name = ''
  const m = email.match(/^ *([\w ]+?) *<(.+)> *$/)
  if (m) {
    name = m[1]
    email = m[2]
  }
  email = email.trim()
  return isEmail(email) ? {name, email: email.toLowerCase()} : null
}

const request_contacts = debounce(
  data => requests.get('ui', `/${session.id}/contacts/lookup-email/`, {args: data}),
  300 // may have to increase this in future
)

export default function () {
  add_listener('fast-email-lookup', async data => {
    const r = parse_address(data.query)
    // TODO search for email addresses in indexeddb
    return r && [r]
  })

  add_listener('slow-email-lookup', async data => {
    try {
      const r = await request_contacts(data)
      return r.data
    } catch (e) {
      if (e === 'canceled') {
        return null
      } else {
        throw e
      }
    }
  })

  add_listener('parse-multiple-addresses', data => {
    let addresses
    if (data.raw.indexOf(',') === -1) {
      // no commas, split on spaces
      addresses = data.raw.split(/[\n ]/)
    } else {
      // includes commas, split on commas
      addresses = data.raw.split(/[\n,]/)
    }
    const results = addresses.filter(v => v).map(parse_address)
    return [results.filter(v => v), results.filter(v => !v).length]
  })
}
