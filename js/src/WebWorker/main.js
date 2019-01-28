import {add_listener} from './utils'

add_listener('testing', async () => {
  console.log('running testing')
  return 42
})
