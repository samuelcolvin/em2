import {sleep} from 'reactstrap-toolbox'
import {make_url, statuses} from '../utils/network'
import Session from './session'
import Websocket from './ws'
import {requests} from './utils'
import Conversations from './conversations'
import Contacts from './contacts'

export default class LogicMain extends EventTarget {
  constructor () {
    super()
    this.ws = new Websocket(this)
    this.session = new Session()
    this.conversations = new Conversations(this)
    this.contacts = new Contacts(this)
    this._conn_status = null
  }

  start = async session_id => {
    await this.session.set(session_id)
    if (this.session.id) {
      await this.update_sessions()
    } else {
      // no session, check the internet connection
      const url = make_url('ui', '/online/')
      try {
        await fetch(url, {method: 'HEAD'})
      } catch (error) {
        // generally TypeError: failed to fetch, also CSP if rules are messed up
        this.set_conn_status(statuses.offline)
        console.debug(`checking connection status at ${url}: offline`)
        return
      }
      console.debug(`checking connection status at ${url}: online`)
      this.set_conn_status(statuses.online)
    }
  }

  update_sessions = async () => {
    this.fire('setUser', this.session.current)
    this.fire('setState', {other_sessions: await this.session.other_sessions()})
    await this.ws.connect()
  }

  switch_session = async session_id => {
    await this.session.set(session_id)
    await this.update_sessions()
    return {email: this.session.email, name: this.session.name}
  }

  auth_token = async data => {
    await requests.post('ui', '/auth/token/', {auth_token: data.auth_token})
    delete data.session.ts
    data.session.cache = new Set()
    await this.session.add(data.session)
    await this.update_sessions()
    return {email: data.session.email, name: data.session.name}
  }

  logout = async () => {
    this.ws.close()
    await requests.post('ui', `/${this.session.id}/auth/logout/`)
    await this.session.delete()
    if (this.session.id) {
      await this.update_sessions()
    } else {
      this.fire('setUser', null)
      this.fire('setState', {other_sessions: []})
    }
  }

  fire = (channel, detail={}) => {
    const event = new CustomEvent(channel, {detail})
    this.dispatchEvent(event)
  }


  set_conn_status = conn_status => {
    if (conn_status !== this._conn_status) {
      this._conn_status = conn_status
      this.fire('setState', {conn_status})
    }
  }

  get_conn_status = async () => {
    for (let i = 0; i < 20; i++) {
      if (![null, statuses.connecting].includes(this._conn_status)) {
        return this._conn_status
      }
      await sleep(50)
    }
    return this._conn_status
  }
}
