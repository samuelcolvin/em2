// based on CRA service worker http://bit.ly/CRA-PWA

function init_sw (r) {
  r.onupdatefound = () => {
    const installingWorker = r.installing
    if (installingWorker == null) {
      return
    }
    installingWorker.onstatechange = () => {
      if (installingWorker.state === 'installed') {
        if (navigator.serviceWorker.controller) {
          // TODO warn this user
          console.log('New content is available and will be used when all tabs for this page are closed.')
        } else {
          console.log('Content is cached for offline use.')
        }
      }
    }
  }
}

export function register_service_worker () {
  if ('serviceWorker' in navigator) {
    const url = `${process.env.PUBLIC_URL}/service-worker.js`
    window.addEventListener('load', () => navigator.serviceWorker.register(url).then(init_sw))
  } else {
    // TODO display to user
    console.warn("service worker not available, app won't run properly")
  }
}

export function unregister_service_worker () {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready.then(r => r.unregister())
  }
}
