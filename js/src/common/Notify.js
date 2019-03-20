import React from 'react'
import {withRouter} from 'react-router-dom'
import WithContext from '../lib/context'

class Notify extends React.Component {
  last_event = new Date()

  on_event = () => {
    this.last_event = new Date()
  }

  since_event = () => (new Date()) - this.last_event

  componentDidMount () {
    this.props.ctx.worker.add_listener('notify', this.notify)
    document.addEventListener('keydown', this.on_event)
    document.addEventListener('mousemove', this.on_event)
  }

  componentWillUnmount() {
    document.removeEventListener('keydown', this.on_event)
    document.removeEventListener('mousemove', this.on_event)
  }

  show_notification = msg => {
    if (!document.hidden && this.since_event() < 5000) {
      this.props.ctx.setMessage(`${msg.title}: ${msg.body}`)
    } else {
      const n = new Notification(msg.title, {
        body: msg.body,
        icon: '/images/notification.png'
      })
      n.onclick = () => {
        // TODO go to the conversation
        window.focus()
        n.close()
      }
    }
  }

  notify = msg => {
    if (!('Notification' in window)) {
      console.warn('This browser does not support desktop notification')
    } else if (msg === 'request') {
      if (Notification.permission === 'default') {
        Notification.requestPermission()
      }
    } else if (Notification.permission === 'granted') {
      this.show_notification(msg)
    } else {
      console.warn('notifications not permitted:', msg)
    }
  }

  render () {
    return null
  }
}
export default WithContext(withRouter(Notify))
