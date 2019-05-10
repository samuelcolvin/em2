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
    this._debounce_lookup = debounce(this._raw_lookup, 300)
  }

  fast_email_lookup = async query => {
    const r = parse_address(query)
    // TODO search for email addresses in indexeddb
    return r && [r]
  }

  slow_email_lookup = async query => {
    try {
      const r = await this._debounce_lookup(query)
      return r.data
    } catch (e) {
      if (e === 'canceled') {
        return null
      } else {
        throw e
      }
    }
  }

  parse_multiple_addresses = raw => {
    let addresses
    if (raw.indexOf(',') === -1) {
      // no commas, split on spaces
      addresses = raw.split(/[\n ]/)
    } else {
      // includes commas, split on commas
      addresses = raw.split(/[\n,]/)
    }
    const results = addresses.filter(v => v).map(parse_address)
    return [results.filter(v => v), results.filter(v => !v).length]
  }

  _raw_lookup = query => requests.get('ui', `/${this._main.session.id}/contacts/lookup-email/`, {args: {query}})
}
