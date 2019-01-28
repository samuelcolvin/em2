export function window_trigger (method, args) {
  postMessage({method: method, args: args})
}

export const LISTENERS = {}

export function add_listener (name, listener) {
  LISTENERS[name || listener.name] = listener
}

export function route_message (message) {
  const method = LISTENERS[message.data.method]
  if (method === undefined) {
    console.error(`worker: method "${message.data.method}" not found`)
    if (message.data.async_id) {
      postMessage({error: `method "${message.data.method}" not found`, async_id: message.data.async_id})
    }
  } else {
    // console.log('worker running:', message.data.method, message.data.call_args || '')
    let result = method(message.data.call_args)

    const on_error = err => {
      console.warn('worker error:', err.details, err)
      const error = {message: err.message || err.toString(), details: err.details}
      postMessage({error, async_id: message.data.async_id})
    }

    if (result.then) {
      result.then(
        result => postMessage({result, async_id: message.data.async_id}),
        err => on_error(err)
      )
    } else {
      try {
        postMessage({result, async_id: message.data.async_id})
      } catch (err) {
        on_error(err)
      }
    }
  }
}
