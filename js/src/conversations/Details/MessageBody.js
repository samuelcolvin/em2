import React from 'react'
import ReactMarkdown from 'react-markdown'

// TODO, need to and cache all fonts and image when the message is received. Anything else?
const IFRAME_CSP = [
  `default-src 'none'`,
  `script-src ${window.location.origin}`,
  `style-src 'unsafe-inline'`,
  `font-src 'unsafe-inline'`,
  `img-src 'unsafe-inline' *`,
].join(';')

const iframe_src_base64 = msg => btoa(`
<!doctype html>
<html lang="en">
  <head>
    <title>${msg.first_action}</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <meta http-equiv="Content-Security-Policy" content="${IFRAME_CSP}">
    <script src="${window.location.origin}/iframes/html-message.js"></script>
  </head>
  <body>${msg.body}</body>
</html>`)

class Html extends React.Component {
  state = {height: 0}

  on_message = event => {
    if (event.origin === 'null' && event.data.iframe_id === this.props.msg.first_action) {
      if (event.data.height) {
        this.setState({height: event.data.height})
      } else if (event.data.href) {
        // checked with https://mathiasbynens.github.io/rel-noopener/malicious.html for opener
        // and https://httpbin.org/get for referer
        const a = document.createElement('a')
        a.href = event.data.href
        a.target = '_blank'
        a.rel = 'noopener noreferrer'
        a.click()
      }
    }
  }

  async componentDidMount () {
    window.addEventListener('message', this.on_message)
  }

  componentWillUnmount () {
    window.removeEventListener('message', this.on_message)
  }

  render () {
    const msg = this.props.msg
    return (
      <iframe
        id={msg.first_action}
        title={msg.first_action}
        className="msg-iframe"
        frameBorder="0"
        scrolling="no"
        sandbox="allow-scripts"
        src={`data:text/html;base64,${iframe_src_base64(msg)}`}
        style={{height: this.state.height + 'px'}}
      />
    )
  }
}

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
