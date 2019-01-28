import {LISTENERS} from './utils'

onmessage = message => { // eslint-disable-line no-undef
  const method = LISTENERS[message.data.method]
  if (method === undefined) {
    console.error(`worker: method "${message.data.method}" not found`)
    if (message.data.async_id) {
      postMessage({error: `method "${message.data.method}" not found`, async_id: message.data.async_id})
    }
  } else {
    // console.log('worker running:', message.data.method, message.data.args || '')
    let result = method(message.data.arg)
    if (message.data.async_id) {
      if (result.then) {
        result.then(
          result => postMessage({result, async_id: message.data.async_id}),
          reason => {
            console.error('worker promise error:', reason)
            postMessage({error: reason.toString(), async_id: message.data.async_id})
          }
        )
      } else {
        try {
          postMessage({result: result, async_id: message.data.async_id})
        } catch (error) {
          console.error('worker promise error:', error)
          postMessage({error, async_id: message.data.async_id})
        }
      }
    }
  }
}

import './main'
