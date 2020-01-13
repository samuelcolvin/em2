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

  lookup_details = async p => {
    // deep copy of participants
    const contacts = {...p}
    let emails = Object.keys(contacts)
    console.log(this._main.session.current)
    if (!emails.length) {
      return contacts
    }

    const update_contacts = contact_details => {
      for (let [email, details] of Object.entries(contact_details)) {
        const contact = contacts[email]
        if (contact) {
          // avoid mutating contact since contacts is only a shallow copy of p
          contacts[email] = Object.assign({}, contact, details)
        }
      }
    }
    update_contacts({[this._main.session.current.email]: {you: true}})

    const now = Math.round(new Date().getTime() / 1000)
    const old = now - 24 * 3600
    const results = await this._main.session.db.contacts
      .where('email').anyOf(emails).filter(c => c.last_updated > old).toArray()
    if (results.length) {
      const db_contacts = Object.assign(...results.map(c => ({[c.email]: c})))
      update_contacts(db_contacts)
      const db_emails = new Set(Object.keys(db_contacts))
      emails = emails.filter(e => !db_emails.has(e))
      if (!emails.length) {
        // we've got details locally of all contacts, no need to look up db
        return contacts
      }
    }
    const online = await this._main.online()
    if (!online) {
      return contacts
    }
    const path = `/${this._main.session.id}/contacts/email-lookup/`
    const r = await this._requests.get('ui', path, {emails})

    if (Object.keys(r.data).length) {
      update_contacts(r.data)
      await this._main.session.db.contacts.bulkPut(Object.entries(r.data)
        .map(([email, c]) => ({...c, email: email, last_updated: now})))
    }
    return contacts
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
