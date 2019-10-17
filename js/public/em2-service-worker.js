self.addEventListener('install', e => {
  console.debug('new service worker installed', e)
  // reload to use the new service worker:
  self.skipWaiting()
})

function push_to_client (client, data) {
  return new Promise(resolve=> {
    const msg_chan = new MessageChannel()
    msg_chan.port1.onmessage = event => resolve(event.data)
    client.postMessage(data, [msg_chan.port2])
  })
}

const meta_action_types = new Set([
  'seen',
  'subject:release',
  'subject:lock',
  'message:lock',
  'message:release',
])

function should_notify (data) {
  if (!data.actions || !data.actions.find(a => a.actor !== data.user_email)) {
    // actions are all by "you"
    return false
  } else if (data.spam) {
    // conversation is spam
    return false
  } else {
    // otherwise check if there are any non-meta actions
    return Boolean(data.actions.find(a => !meta_action_types.has(a.act)))
  }
}

async function on_push (event) {
  const data = event.data.json()
  console.debug('Received a push event:', data)
  if (data === 'check') {
    return
  }
  let notification = null
  if (should_notify(data)) {
    notification = {
      title: data.conv_details.sub,
      body: `${data.actions[0].actor}: ${data.conv_details.prev}`,
      data: {
        user_id: data.user_id,
        link: `/${data.conversation.substr(0, 10)}/`,
      },
      badge: '/android-chrome-192x192.png',  // image in notification bar
      icon: './android-chrome-512x512.png', // image next message in notification on android
    }
  }
  const clients = await self.clients.matchAll({type: 'window'})
  const client_data = Object.assign({}, data, {notification})
  const window_answers = await Promise.all(clients.map(client => push_to_client(client, client_data)))
  if (notification && !window_answers.find(a => a)) {
    console.debug('Received a push message, showing notification:', data)
    // (await self.registration.getNotifications()).forEach(n => n.close())
    await self.registration.showNotification(notification.title, notification)
  } else {
    console.debug('Received a push message, not showing notification:', data)
  }
}
self.addEventListener('push', event => event.waitUntil(on_push(event)))

async function click (event) {
  console.debug('sw notification clicked: ', event)
  event.notification.close()

  const clients = await self.clients.matchAll({type: 'window'})
  let found_client = false
  for (let client of clients) {
    await push_to_client(client, event.notification.data)
    if ('focus' in client) {
      await client.focus()
    }
    found_client = true
  }
  if (!found_client) {
    await self.clients.openWindow(event.notification.data.link)
  }
}
self.addEventListener('notificationclick', event => event.waitUntil(click(event)))
