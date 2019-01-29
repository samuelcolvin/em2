import requests, {conn_status} from '../lib/requests'
import {add_listener} from './utils'


add_listener('list-conversations', async data => {
  // try and get conversations from indexeddb
  const r = await requests.get('ui', `/list/?page=${data.page}`, {allow_fail: true})
  console.log('list-conversations response:', r)
  if (conn_status[r]) {
    return r
  }
  return []
})


add_listener('auth-token', async data => {
  console.log('auth-token:', data)
  const r = await requests.post('ui', '/auth-token/', {auth_token: data.auth_token})
  console.log('auth-token response:', r)
  return {}
})
