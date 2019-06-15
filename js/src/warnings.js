
export default function () {
  const warnings = []
  if (!('serviceWorker' in navigator)) {
    warnings.push('serviceWorker')
  }
  if (!('showNotification' in ServiceWorkerRegistration.prototype)) {
    warnings.push('showNotification')
  }
  if (!('PushManager' in window)) {
    warnings.push('PushManager')
  }
  if (warnings.length) {
    console.warn('Browser not supported, the following features are not supported:', warnings)
  }
  return warnings
}
