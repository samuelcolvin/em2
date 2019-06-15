export async function init_sw () {
  const r = await navigator.serviceWorker.register(process.env.PUBLIC_URL + '/em2-service-worker.js')
  r.onupdatefound = () => {
    const installing_worker = r.installing
    if (installing_worker !== null) {
      installing_worker.onstatechange = () => {
        if (installing_worker.state === 'installed') {
          if (navigator.serviceWorker.controller) {
            // TODO warn user
            console.log('PLEASE RELOAD!')
          } else {
            console.log('Content is cached for offline use.')
          }
        }
      }
    }
  }
}

export function register_service_worker () {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', init_sw)
  }
}

export function unregister_service_worker () {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready.then(r => r.unregister())
  }
}
