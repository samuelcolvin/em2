import debounce from 'debounce-async'
import isEmail from 'validator/lib/isEmail'
import ndjsonStream from 'can-ndjson-stream'

function parse_address (email) {
  let main_name = ''
  const m = email.match(/^ *([\w ]*?) *<(.+)> *$/)
  if (m) {
    main_name = m[1]
    email = m[2]
  }
  email = email.trim()
  return isEmail(email) ? {main_name, email: email.toLowerCase()} : null
}

export default class Contacts {
  constructor (main) {
    this._main = main
    this._debounce_lookup = debounce(this._raw_lookup, 300)
    this._requests = this._main.requests
  }

  list = async page => {
    const online = await this._main.online()
    if (online) {
      const r = await this._requests.get('ui', `/${this._main.session.id}/contacts/`, {page})
      return r.data
    }
    return {}
  }

  details = async id => {
    const online = await this._main.online()
    if (online) {
      const r = await this._requests.get('ui', `/${this._main.session.id}/contacts/${id}/`)
      return r.data
    }
    return null
  }

  create = async data => {
    return await this._requests.post(
      'ui', `/${this._main.session.id}/contacts/create/`, data, {expected_status: [201, 400, 409]}
    )
  }

  edit_initial = async id => {
    const online = await this._main.online()
    if (online) {
      const r = await this._requests.get('ui', `/${this._main.session.id}/contacts/${id}/edit/`)
      return r.data
    }
    return {}
  }

  edit = async data => {
    return await this._requests.post(
      'ui', `/${this._main.session.id}/contacts/${data.id}/edit/`, data, {expected_status: [200, 400, 409]}
    )
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

  request_image_upload = async (filename, content_type, size) => {
    const args = {filename, content_type, size}
    const r = await this._requests.get('ui', `/${this._main.session.id}/contacts/upload-image/`, args)
    return r.data
  }

  _raw_lookup = async (query, callback) => {
    const config = {raw_response: true, headers: {'Accept': 'text/plain'}}
    const r = await this._requests.get('ui', `/${this._main.session.id}/contacts/search/`, {query}, config)
    const stream = await ndjsonStream(r.body)
    const reader = stream.getReader()
    let s = await reader.read()
    while (!s.done) {
      callback(s.value)
      s = await reader.read()
    }
  }
}
