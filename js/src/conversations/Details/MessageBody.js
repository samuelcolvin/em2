import React from 'react'
import ReactMarkdown from 'react-markdown'
import {sleep} from '../../lib'

// TODO, need to and cache all fonts and image when the message is received. Anything else?
// const iframe_csp = [
//   `default-src 'none'`,
//   `script-src 'sha256-9/tp0gG/02uaXhcWrCrvIbnLd/X1O+W8mGAk6amY/ho='`,
//   `style-src 'unsafe-inline'`,
//   `font-src 'unsafe-inline'`,
//   `img-src 'unsafe-inline' *`,
// ].join(';')


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

  update_iframe = msg => {
    this.iframe_ref.current.contentWindow.postMessage({
      body: msg.body,
      iframe_id: msg.first_action,
    }, '*')
  }

  componentDidUpdate() {
    this.update_iframe(this.props.msg)
  }

  async componentDidMount () {
    window.addEventListener('message', this.on_message)
    await sleep(50)
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
