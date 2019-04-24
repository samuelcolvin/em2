
export function make_url (app_name, path) {
  if (path.match(/^https?:\//)) {
    return path
  } else {
    if (!path.startsWith('/')) {
      throw Error('path must start with "/"')
    }
    if (app_name !== 'ui' && app_name !== 'auth') {
      throw Error('app_name must be "ui" or "auth"')
    }

    if (process.env.REACT_APP_DOMAIN === 'localhost') {
      return `http://localhost:8000/${app_name}${path}`
    } else {
      return `https://${app_name}.${process.env.REACT_APP_DOMAIN}${path}`
    }
  }
}

export const statuses = {
  offline: 'offline',
  connecting: 'connecting',
  online: 'online',
}
