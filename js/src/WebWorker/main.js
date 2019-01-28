import requests from '../lib/requests'
import {add_listener} from './utils'


add_listener('list-conversations', async arg => {
  const r = await requests.get('ui', `/list/?page=${arg.page}`)
  console.log('response:', r)
  return []
})
