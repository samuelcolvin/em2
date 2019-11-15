import * as fas from '@fortawesome/free-solid-svg-icons'
import {on_mobile} from 'reactstrap-toolbox'
import {statuses, get_version} from './network'

const online_interval = 30e3
const offline_interval = 10e3

export default class WebPush {
  constructor (realtime) {
    this._realtime = realtime
    this._main = realtime._main
    this._do_notifications = !on_mobile
    this._clear_inverval = 0
  }

  close = () => {
    this._unsubscribe()
    clearTimeout(this._clear_inverval)
  }

  connect = async () => {
    if (!('serviceWorker' in navigator) ||
      !('showNotification' in ServiceWorkerRegistration.prototype) ||
      !('PushManager' in window)) {
      return false
    }
    this._clear_inverval = setTimeout(this._check_online, online_interval)
    this._main.set_conn_status(statuses.connecting)
    const sub = await this._subscribe()
    if (!sub) {
      // unable to subscribe return and fallback to websockets
      clearTimeout(this._clear_inverval)
      return false
    }
    navigator.serviceWorker.addEventListener('message', this.on_message)
    // TODO, might need to catch errors or at least report on this?
    this._main.requests.post('ui', `/${this._main.session.id}/webpush-subscribe/`, sub.toJSON())
    this._main.set_conn_status(statuses.online)
    return true
  }

  _subscribe = async () => {
    // We need the service worker registration to check for a subscription
    const sw_registration = await sw_ready()
    navigator.serviceWorker.addEventListener('message', this.on_message)
    let sub = await sw_registration.pushManager.getSubscription()
    if (sub) {
      console.debug('found existing active web-push subscription')
      return sub
    }

    try {
      sub = await sw_registration.pushManager.subscribe({applicationServerKey, userVisibleOnly: true})
    } catch (e) {
      if (Notification.permission === 'denied') {
        console.debug('Permission for Notifications was denied')
        return
      } else {
        throw e
      }
    }
    console.debug('new web-push subscription created')
    return sub
  }

  _unsubscribe = async () => {
    const sw_registration = await sw_ready()
    const sub = await sw_registration.pushManager.getSubscription()
    if (sub) {
      const sub_info = sub.toJSON()
      await sub.unsubscribe()
      await this._main.requests.post('ui', `/${this._main.session.id}/webpush-unsubscribe/`, sub_info)
    }
  }

  on_message = event => {
    // FIXME work out what the error here is
    console.debug('web_push on_message', event, this._main.session.current)
    if (!event.data || (event.data.user_id !== this._main.session.current.user_id)) {
      event.ports[0].postMessage(false)
      return
    }

    if (event.data.link) {
      // message after clicking on notification, follow link
      event.ports[0].postMessage(null)
      if (event.data.link !== window.location.pathname) {
        this._main.history.push(event.data.link)
      }
      return
    }

    if (this._do_notifications && event.data.notification && this._main.notify.window_active()) {
      event.ports[0].postMessage(true)
      this._main.notify.notify({...event.data.notification, toast_icon: fas.faEnvelope})
    } else {
      event.ports[0].postMessage(false)
    }
    this._realtime.on_message(event.data)
  }

  _check_online = async () => {
    let interval
    if (await get_version()) {
      interval = online_interval
      this._main.set_conn_status(statuses.online)
    } else {
      interval = offline_interval
      this._main.set_conn_status(statuses.offline)
    }
    this._clear_inverval = setTimeout(() => this._check_online(), interval)
  }
}


function UrlBase64ToUint8Array (base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  return Uint8Array.from([...rawData].map(char => char.charCodeAt(0)))
}

const applicationServerKey = UrlBase64ToUint8Array(process.env.REACT_APP_PUSH_API_KEY)

function sw_ready () {
  return new Promise((resolve, reject) => {
    navigator.serviceWorker.ready.then(resolve).catch(reject)
    setTimeout(() => reject('navigator.serviceWorker.ready timed out'), 2000)
  })
}
