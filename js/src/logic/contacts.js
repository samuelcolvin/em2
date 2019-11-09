import debounce from 'debounce-async'
import isEmail from 'validator/lib/isEmail'
import ndjsonStream from 'can-ndjson-stream'

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

  email_lookup = async (query, callback) => {
    const raw_email = parse_address(query)
    // TODO search for email addresses in indexeddb
    if (raw_email) {
      callback(raw_email)
    }
    try {
      await this._debounce_lookup(query, callback)
    } catch (e) {
      console.log('xxx', e)
      if (e !== 'canceled') {
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

  _raw_lookup = async (query, callback) => {
    const config = {raw_response: true, headers: {'Accept': 'application/x-ndjson'}}
    const r = await this._main.requests.get('ui', `/${this._main.session.id}/contacts/lookup-email/`, {query}, config)
    const stream = await ndjsonStream(r.body)
    const reader = stream.getReader()
    let s = await reader.read()
    while (!s.done) {
      callback(s.value)
      s = await reader.read()
    }
  }
}
