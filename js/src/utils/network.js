
export function make_url (app_name, path) {
  if (!path.startsWith('/')) {
    throw Error('path must start with "/"')
  } else if (app_name !== 'ui' && app_name !== 'auth') {
    throw Error('app_name must be "ui" or "auth"')
  } else if (process.env.REACT_APP_DOMAIN === 'localhost') {
    return `http://localhost:8000/${app_name}${path}`
  } else {
    return `https://${app_name}.${process.env.REACT_APP_DOMAIN}${path}`
  }
}

export const statuses = {
  offline: 'offline',
  connecting: 'connecting',
  online: 'online',
}
