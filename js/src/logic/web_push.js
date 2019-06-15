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

function on_sw_message (event) {
  event.ports[0].postMessage(null)
  console.log('got message: ', event)
}

export async function get_subscription () {
  if (!('serviceWorker' in navigator) ||
      !('showNotification' in ServiceWorkerRegistration.prototype) ||
      !('PushManager' in window)) {
    return
  }

  // We need the service worker registration to check for a subscription
  const sw_registration = await sw_ready()
  navigator.serviceWorker.addEventListener('message', on_sw_message)
  let sub
  try {
    sub = await sw_registration.pushManager.getSubscription()
  } catch (err) {
    console.warn('Error during getSubscription()', err)
    return
  }
  if (sub) {
    // already subscribed, no need to do anything
    console.log('already subscribed')
    const sub_info = JSON.stringify(sub.toJSON())
    console.log('sub info:', sub_info)
    return
  }
  try {
    sub = await sw_registration.pushManager.subscribe({applicationServerKey, userVisibleOnly: true})
  } catch (e) {
    if (Notification.permission === 'denied') {
      console.log('Permission for Notifications was denied')
    } else {
      console.error('Unable to subscribe to push.', e)
    }
    return
  }
  console.log('subscription successful, sub:', sub)
  const sub_info = JSON.stringify(sub.toJSON())
  console.log('sub info:', sub_info)
}
