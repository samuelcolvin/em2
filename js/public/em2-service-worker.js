self.addEventListener('install', e => {
  console.log('new service worker installed', e)
  self.skipWaiting()
})

function push_to_client (client, msg) {
  return new Promise(resolve=> {
    const msg_chan = new MessageChannel()
    msg_chan.port1.onmessage = event => resolve(event.data)
    client.postMessage(msg, [msg_chan.port2])
  })
}

async function on_push (event) {
  const data = event.data.json()
  console.debug('Received a push message:', data)
  if (data === 'check') {
    return
  }
  const notifications = await self.registration.getNotifications()
  notifications.forEach(n => n.close())
  await self.registration.showNotification('new message', {
    body: data,
    // badge: './image-in-notification-bar-on-android.png',
    // icon: './image-next-message-in-notification-on-android.png',
  })
  const clients = await self.clients.matchAll({type: 'window'})
  await Promise.all(clients.map(client => push_to_client(client, data)))
}
self.addEventListener('push', event => event.waitUntil(on_push(event)))

async function click (event) {
  console.log('On notification click: ', event)
  event.notification.close()

  // await self.clients.openWindow('/')
  // This looks to see if the current is already open and
  // focuses if it is
  const clients = await self.clients.matchAll({type: 'window'})
  for (let client of clients) {
    // console.log('client', client)
    // TODO check url
    if ('focus' in client) {
      await client.focus()
      return
    }
  }
  await self.clients.openWindow('/')
}
self.addEventListener('notificationclick', event => event.waitUntil(click(event)))
