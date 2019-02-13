import React from 'react'

export default ({src, title, id}) => (
  <div className="iframe-container">
    <div className="zero-height d-flex justify-content-center">
      Loading...
    </div>
    <iframe
        id={id}
        title={title}
        frameBorder="0"
        scrolling="no"
        sandbox="allow-forms allow-scripts"
        src={src}
    />
  </div>
)
