import React from 'react'

export default class IFrame extends React.Component {
  shouldComponentUpdate (nextProps) {
    return false
  }

  render () {
    return (
      <div className="iframe-container">
        <div className="zero-height d-flex justify-content-center">
          Loading...
        </div>
        <iframe
            ref={this.props.iframe_ref}
            title="Login"
            frameBorder="0"
            scrolling="no"
            sandbox="allow-forms allow-scripts"
            src="/auth-iframes/login.html"
        />
      </div>
    )
  }
}
