import React from 'react'
import ReactMarkdown from 'react-markdown'
import {sleep} from '../../lib'


class Html extends React.Component {
  iframe_ref = React.createRef()

  on_message = event => {
    if (event.origin === 'null' && event.data.iframe_id === this.props.msg.first_action.toString()) {
      if (event.data.height) {
        // do this rather than keeping height in state to avoid rendering the iframe multiple times
        this.iframe_ref.current.style.height = event.data.height + 'px'
      } else if (event.data.href) {
        // checked with https://mathiasbynens.github.io/rel-noopener/ for opener
        // and https://httpbin.org/get for referer
        const a = document.createElement('a')
        a.href = event.data.href
        a.target = '_blank'
        a.rel = 'noopener noreferrer'
        a.click()
      }
    }
  }

  update_iframe = async msg => {
    await sleep(50)
    this.iframe_ref.current.contentWindow.postMessage({
      body: msg.body,
      iframe_id: msg.first_action,
    }, '*')
  }

  componentDidUpdate () {
    this.update_iframe(this.props.msg)
  }

  componentDidMount () {
    window.addEventListener('message', this.on_message)
    this.update_iframe(this.props.msg)
  }

  componentWillUnmount () {
    window.removeEventListener('message', this.on_message)
  }

  shouldComponentUpdate (nextProps) {
    return this.props.msg.first_action !== nextProps.msg.first_action || this.props.msg.body !== nextProps.msg.body
  }

  render () {
    return (
      <iframe
        ref={this.iframe_ref}
        title={this.props.msg.first_action}
        className="msg-iframe"
        frameBorder="0"
        scrolling="no"
        sandbox="allow-scripts"
        src="/iframes/message/message.html"
      />
    )
  }
}

// TODO following local links, eg. to conversations, block links to settings
const markdown_props = {
  renderers: {
    link: props => <a href={props.href} target="_blank" rel="noopener noreferrer">{props.children}</a>,
  },
}

export default ({msg}) => {
  if (msg.format === 'markdown') {
    return <ReactMarkdown {...markdown_props} source={msg.body}/>
  } else if (msg.format === 'html') {
    return <Html msg={msg}/>
  } else {
    // plain
    return <div>{msg.body}</div>
  }
}
