import debounce from 'debounce-async'
import isEmail from 'validator/lib/isEmail'
import {requests} from './utils'

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

export default class Contacts {
  constructor (main) {
    this._main = main
    this._sess = main.session
    this._debounce_request_contacts = debounce(this._raw_request_contacts, 300)
  }

  fast_email_lookup = async data => {
    const r = parse_address(data.query)
    // TODO search for email addresses in indexeddb
    return r && [r]
  }

  slow_email_lookup = async data => {
    try {
      const r = await this._debounce_request_contacts(data)
      return r.data
    } catch (e) {
      if (e === 'canceled') {
        return null
      } else {
        throw e
      }
    }
  }

  parse_multiple_addresses = data => {
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
  }

  _raw_request_contacts = data => {
    requests.get('ui', `/${this._sess.id}/contacts/lookup-email/`, {args: data})
  }
}
