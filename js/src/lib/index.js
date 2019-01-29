export const unique = (value, index, array) => array.indexOf(value) === index

export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

export const as_title = s => s.replace(/(_|-)/g, ' ').replace(/(_|\b)\w/g, l => l.toUpperCase())

export const get_component_name = Comp => Comp.displayName || Comp.name || 'Component'

export const on_mobile = /mobile|ip(hone|od|ad)|android|blackberry|opera mini/i.test(navigator.userAgent)

export class DetailedError extends Error {
  constructor (message, details) {
    super()
    this.message = message
    this.details = details
  }
}

export function load_script (url) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${url}"]`)) {
      // script already loaded
      resolve()
    } else {
      const script = document.createElement('script')
      script.src = url
      script.onerror = e => reject(e)
      script.onload = () => resolve()
      document.body.appendChild(script)
      setTimeout(() => reject(`script "${url}" timed out`), 8000)
    }
  })
}
