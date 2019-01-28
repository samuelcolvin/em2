import MainWorker from './WebWorker/load.js'

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

    this.add_listener = this.add_listener.bind(this)
    this.remove_listener = this.remove_listener.bind(this)
    this._onmessage = this._onmessage.bind(this)
    this.execute = this.execute.bind(this)
    this.fetch = this.fetch.bind(this)

    this.worker.onmessage = this._onmessage
  }

  add_listener (name, listener) {
    const id = random()
    this.listeners[id] = {func: listener, name: name || listener.name}
    return id
  }

  remove_listener (id) {
    delete this.listeners[id]
  }

  _onmessage (message) {
    if (message.data.async_id) {
      const resolver = this.rosolvers[message.data.async_id]
      if (message.data.error) {
        this.app.setError({message: `Error on worker: ${message.data.error}`})
        resolver.reject(message.data.error)
      } else {
        resolver.resolve(message.data.result)
      }
    } else if (message.data.method) {
      for (const l of Object.values(this.listeners)) {
        if (l.name === message.data.method) {
          // console.log('window running:', message.data.method, message.data.args || '')
          l.func(message.data.args || {})
        }
      }
    } else {
      console.error('worker message with no method or async_id:', message)
    }
  }

  execute (method, ...args) {
    this.worker.postMessage({method: method, args: args})
  }

  fetch (method, arg, timeout) {
    return new Promise((resolve, reject) => {
      const clear = setTimeout(() => {
        const message = `worker fetch timed out, method "${method}"`
        this.app.setError({message})
        reject(message)
      }, timeout || 2000)
      const id = random()
      this.rosolvers[id] = {
        resolve: (...args) => {
          delete this.rosolvers[id]
          clearInterval(clear)
          resolve(...args)
        },
        reject: (...args) => {
          delete this.rosolvers[id]
          clearInterval(clear)
          this.app.setError({message: `Error on worker: ${args}`})
          reject(...args)
        },
      }
      this.worker.postMessage({method: method, arg: arg, async_id: id})
    })
  }
}

export default Worker
