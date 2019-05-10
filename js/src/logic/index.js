import {sleep, Notify} from 'reactstrap-toolbox'
import {make_url, statuses} from '../utils/network'
import Session from './session'
import Websocket from './ws'
import Conversations from './conversations'
import Contacts from './contacts'
import Auth from './auth'

const random = () => Math.floor(Math.random() * 1e6)

export default class LogicMain {
  constructor (history) {
    this.notify = new Notify(history)
    this.listeners = {}
    this.ws = new Websocket(this)
    this.session = new Session(this)
    this.conversations = new Conversations(this)
    this.contacts = new Contacts(this)
    this.auth = new Auth(this)
    this._conn_status = null
    this._start()
  }

  _start = async () => {
    const session_id = JSON.parse(sessionStorage['session_id'] || 'null')
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

  add_listener = (channel, listener) => {
    const id = random()
    this.listeners[id] = {func: listener, channel}
    return () => {
      delete this.listeners[id]
    }
  }

  fire = (channel, details={}) => {
    let matched = 0
    for (const l of Object.values(this.listeners)) {
      if (l.channel === channel) {
        console.debug(`channel "${channel}", calling "${l.func}" with`, details)
        l.func(details)
        matched += 1
      }
    }
    if (matched === 0) {
      console.debug(`message to channel "${channel}", with no listeners`)
    }
  }
}
