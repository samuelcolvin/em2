export function register_service_worker () {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register(process.env.PUBLIC_URL + '/em2-service-worker.js')
    })
  }
}

export function unregister_service_worker () {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.ready.then(r => r.unregister())
  }
}
