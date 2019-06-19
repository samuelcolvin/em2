import {sleep, Notify} from 'reactstrap-toolbox'
import {statuses, Requests, online} from './network'
import Session from './session'
import RealTime from './realtime'
import Conversations from './conversations'
import Serach from './search'
import Contacts from './contacts'
import Auth from './auth'

const random = () => Math.floor(Math.random() * 1e6)

export default class LogicMain {
  constructor (history) {
    this.listeners = {}
    this.history = history
    this.notify = new Notify(history)
    this.requests = new Requests(this)
    this.realtime = new RealTime(this)
    this.session = new Session(this)
    this.conversations = new Conversations(this)
    this.search = new Serach(this)
    this.contacts = new Contacts(this)
    this.auth = new Auth(this)
    this._conn_status = null
    this._start()
  }

  _start = async () => {
    await this.session.init()
    if (this.session.id) {
      return
    }
    // no session, check the internet connection
    if (await online()) {
      console.debug(`checking connection status: online`)
      this.set_conn_status(statuses.online)
    } else {
      this.set_conn_status(statuses.offline)
      console.debug(`checking connection status: offline`)
    }
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

  online = async () => statuses.online === await this.get_conn_status()

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
        l.func(details)
        matched += 1
      }
    }
    console.debug(`event "${channel}" fired to ${matched} listener${matched === 1 ? '' : 's'} with args:`, details)
  }
}
