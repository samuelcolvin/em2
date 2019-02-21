import React from 'react'
import ReactMarkdown from 'react-markdown'

// TODO, need to and cache all fonts and image when the message is received. Anything else?
const iframe_csp = [
  `default-src 'none'`,
  `script-src 'sha256-9/tp0gG/02uaXhcWrCrvIbnLd/X1O+W8mGAk6amY/ho='`,
  `style-src 'unsafe-inline'`,
  `font-src 'unsafe-inline'`,
  `img-src 'unsafe-inline' *`,
].join(';')

const iframe_js = `
const msg = data => window.parent.postMessage(Object.assign(data, {iframe_id: parseInt(document.title)}), '*');
window.onload = () => {
  msg({height: Math.min(500, Math.max(50, document.documentElement.offsetHeight))});
  for(const link of document.links){
    link.onclick = e => {
      e.preventDefault();
      msg({href: link.getAttribute('href')});
    }
  }
}`.replace(/\n */g, '').replace(/ ?(=>?|:|,) /g, '$1')

const iframe_src_base64 = msg => btoa(`
<!doctype html>
<html lang="en">
  <head>
    <title>${msg.first_action}</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no">
    <meta http-equiv="Content-Security-Policy" content="${iframe_csp}">
    <script>${iframe_js}</script>
  </head>
  <body>${msg.body}</body>
</html>`)

class Html extends React.Component {
  iframe_ref = React.createRef()

  on_message = event => {
    if (event.origin === 'null' && event.data.iframe_id === this.props.msg.first_action) {
      if (event.data.height) {
        // do this rather than keeping height in state to avoid rendering the iframe multiple times
        this.iframe_ref.current.style.height = event.data.height + 'px'
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
        src={`data:text/html;base64,${iframe_src_base64(this.props.msg)}`}
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
