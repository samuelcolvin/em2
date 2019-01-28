export function make_url (path) {
  if (path.match(/^https?:\//)) {
    return path
  } else {
    if (!path.startsWith('/')) {
      throw Error('path must start with "/"')
    }
    return process.env.REACT_APP_REQUEST_ORIGIN + '/__' + path
  }
}

export function build_query (args) {
  const arg_list = []
  const add_arg = (n, v) => arg_list.push(encodeURIComponent(n) + '=' + encodeURIComponent(v))
  for (let [name, value] of Object.entries(args)) {
    if (Array.isArray(value)) {
      for (let value_ of value) {
        add_arg(name, value_)
      }
    } else if (value !== null && value !== undefined) {
      add_arg(name, value)
    }
  }
  if (arg_list.length > 0) {
    return '?' + arg_list.join('&')
  }
  return ''
}

export default async function (app, method, path, config) {
  let url = make_url(path)

  config = config || {}
  if (config.args) {
    url += build_query(config.args)
  }

  if (Number.isInteger(config.expected_status)) {
    config.expected_status = [config.expected_status]
  } else {
    config.expected_status = config.expected_status || [200]
  }

  const headers = {'Accept': 'application/json'}
  if (method !== 'GET') {
    headers['Content-Type'] = 'application/json'
  }

  const init = {method: method, headers: headers, credentials: 'include'}
  if (config.send_data) {
    init.body = JSON.stringify(config.send_data)
  }
  let r
  try {
    r = await fetch(url, init)
  } catch (error) {
    const message = error.toString()
    app && app.setError({message, url, init})
    throw Error(message)
  }
  if (config.expected_status.includes(r.status)) {
    const data = await r.json()
    return {data, status: r.status}
  } else {
    let response_data = {}
    try {
      response_data = await r.json()
    } catch (e) {
      // ignore and use normal error
    }
    const message = response_data.message || `Unexpected response ${r.status}`
    app && app.setError({message, status: r.status, url, init, response_data, response: r})
    throw Error(message)
  }
}
