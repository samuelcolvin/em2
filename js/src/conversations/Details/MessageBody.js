import React from 'react'
import {sleep} from 'reactstrap-toolbox'
import {make_url} from '../../logic/network'
import {MarkdownRenderer} from '../../Editor'


class Html extends React.Component {
  iframe_ref = React.createRef()
  loaded = false

  on_message = event => {
    if (event.origin === 'null' && this.props.msg.first_action === event.data.iframe_id) {
      if (event.data.loaded) {
        this.iframe_ref.current.contentWindow.postMessage(this.build_body(), '*')
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

  build_body = () => {
    // extract styles and replace src urls for the following images
    // * inline attachments eg. URLs start with cid:
    // * imgs with urls to external resources
    // * image urls referenced in styles via url(...)

    const msg_el = document.createElement('div')
    // TODO, how can body be empty?
    msg_el.innerHTML = this.props.msg.body || ''

    for (let img of msg_el.querySelectorAll('img')) {
      img.src = img.src.startsWith('cid:') ? this.replace_cid(img.src) : this.img_url(img.src)
    }

    const process_style = el => {
      msg_el.removeChild(el)
      return this.convert_styles(el.innerHTML)
    }

    const styles = [...msg_el.querySelectorAll('style')].map(process_style).join('\n')

    return {body: msg_el.innerHTML, styles}
  }

  replace_cid = src => make_url('ui', `/${this.props.session_id}/conv/${this.props.conv}/cid-image/${src.substr(4)}`)

  img_url = url => make_url('ui', `/${this.props.session_id}/conv/${this.props.conv}/html-image/${btoa(url)}`)

  convert_styles = s => s.replace(/url\((['"]?)((?:https?:)?\/\/.+?)\1\)/gi, (_, __, url) => this.img_url(url))

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

export default ({msg, conv, session_id}) => {
  if (msg.format === 'markdown') {
    return <MarkdownRenderer value={msg.body}/>
  } else if (msg.format === 'html') {
    return <Html msg={msg} conv={conv} session_id={session_id}/>
  } else {
    // plain
    return <div>{msg.body}</div>
  }
}
