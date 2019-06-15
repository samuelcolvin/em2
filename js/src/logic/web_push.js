

export default class WebPush {
  constructor (realtime) {
    this._realtime = realtime
    this._main = realtime._main
  }

  close = () => {
    this._unsubscribe()
  }

  connect = async () => {
    if (!('serviceWorker' in navigator) ||
      !('showNotification' in ServiceWorkerRegistration.prototype) ||
      !('PushManager' in window)) {
      return false
    }
    const sub = await this._subscribe()
    if (!sub) {
      // unable to subscribe return and fallback to websockets
      return false
    }
    navigator.serviceWorker.addEventListener('message', this.on_message)
    await this._main.requests.post('ui', `/${this._main.session.id}/webpush-subscribe/`, sub.toJSON())
    return true
  }

  _subscribe = async () => {
    // We need the service worker registration to check for a subscription
    const sw_registration = await sw_ready()
    navigator.serviceWorker.addEventListener('message', this.on_message)
    let sub = await sw_registration.pushManager.getSubscription()
    if (sub) {
      // already subscribed, no need to do anything else
      console.debug('already subscribed')
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
    console.debug('new subscription successful')
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
    event.ports[0].postMessage(null)
    console.log('got message: ', event)
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
