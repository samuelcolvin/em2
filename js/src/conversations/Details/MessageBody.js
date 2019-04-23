import React from 'react'
import ReactMarkdown from 'react-markdown'
import {sleep} from '../../lib'
import {make_url} from '../../lib/requests'



class Html extends React.Component {
  iframe_ref = React.createRef()
  loaded = false

  on_message = event => {
    if (event.origin === 'null' && this.props.msg.first_action === event.data.iframe_id) {
      if (event.data.loaded) {
        this.iframe_ref.current.contentWindow.postMessage({body: this.build_body()}, '*')
      } else if (event.data.height) {
        // do this rather than keeping height in state to avoid rendering the iframe multiple times
        this.iframe_ref.current.style.height = (event.data.height + 10) + 'px'
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

  async componentDidMount () {
    await sleep(50)
    window.addEventListener('message', this.on_message)
  }

  componentWillUnmount () {
    window.removeEventListener('message', this.on_message)
  }

  build_body = () => this.props.msg.body.replace(/src="cid:(.+?)"/g, this.replace_id)

  replace_id = (m, cid) => {
    const url = make_url('ui', `/${this.props.session_id}/img/${this.props.conv}/${cid}`)
    return `src="${url}"`
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
        src={`${process.env.REACT_APP_IFRAME_MESSAGE}#${this.props.msg.first_action}`}
      />
    )
  }
}

// TODO following local links, eg. to conversations, block links to settings, perhaps move this to an iframe
const markdown_props = {
  renderers: {
    link: props => <a href={props.href} target="_blank" rel="noopener noreferrer">{props.children}</a>,
  },
}

export default ({msg, conv, session_id}) => {
  if (msg.format === 'markdown') {
    return <ReactMarkdown {...markdown_props} source={msg.body}/>
  } else if (msg.format === 'html') {
    return <Html msg={msg} conv={conv} session_id={session_id}/>
  } else {
    // plain
    return <div>{msg.body}</div>
  }
}
