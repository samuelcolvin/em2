export const unique = (value, index, array) => array.indexOf(value) === index

export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

export const as_title = s => s.replace(/(_|-)/g, ' ').replace(/(_|\b)\w/g, l => l.toUpperCase())

export const get_component_name = Comp => Comp.displayName || Comp.name || 'Component'

export const on_mobile = /mobile|ip(hone|od|ad)|android|blackberry|opera mini/i.test(navigator.userAgent)

export class DetailedError extends Error {
  constructor(message, details) {
    super()
    this.message = message
    this.details = details
  }
}
