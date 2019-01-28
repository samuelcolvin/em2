import request, {make_url} from '../lib/requests'

export function window_trigger (method, args) {
  postMessage({method: method, args: args})
}

export const LISTENERS = {}

export function add_listener (name, listener) {
  LISTENERS[name || listener.name] = listener
}

export const requests = {
  get: (path, config) => request(null, 'GET', path, config),
  post: (path, data, config) => {
    config = config || {}
    config.send_data = data
    return request(null, 'POST', path, config)
  }
}
