import MainWorker from './WebWorker/load.js'
import {DetailedError} from './lib'

if (!window) {
  throw Error('WebWorkerRun.js should only be called from the window, not a worker')
}

const random = () => Math.floor(Math.random() * 1e6)


class Worker {
  constructor (app) {
    this.app = app
    this.worker = new MainWorker()
    this.listeners = {}
    this.rosolvers = {}

    this.worker.onmessage = this._onmessage
  }

  add_listener = (name, listener) => {
    const id = random()
    this.listeners[id] = {func: listener, name}
    return id
  }

  remove_listener = id => {
    // TODO maybe not required
    delete this.listeners[id]
  }

  _onmessage = message => {
    if (message.data.async_id) {
      const resolver = this.rosolvers[message.data.async_id]
      if (message.data.error) {
        const err = DetailedError(message.data.error.message, message.data.error.details)
        resolver.reject(err)
      } else {
        resolver.resolve(message.data.result)
      }
    } else if (message.data.method) {
      for (const l of Object.values(this.listeners)) {
        if (l.name === message.data.method) {
          // console.log('window running:', message.data.method, message.data.call_args || '')
          l.func(message.data.call_args || {})
          return
        }
      }
      throw Error(`worker message with method "${message.data.method}" has no listener`)
    } else {
      throw Error(`worker message with no method or async_id: ${message}`)
    }
  }

  call = (method, call_args, timeout) => {
    return new Promise((resolve, reject) => {
      const clear = setTimeout(() => {
        const message = `worker fetch timed out, method "${method}"`
        this.app.setError({message})
        reject(message)
      }, timeout || 8000)

      const id = random()
      this.rosolvers[id] = {
        resolve: result => {
          delete this.rosolvers[id]
          clearInterval(clear)
          resolve(result)
        },
        reject: error => {
          delete this.rosolvers[id]
          clearInterval(clear)
          // this.app.setError(error)
          reject(error)
        },
      }
      this.worker.postMessage({method, call_args, async_id: id})
    })
  }
}

export default Worker
