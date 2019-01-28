import React from 'react'
import {withRouter} from 'react-router-dom'

export const Error = ({error}) => {
  if (error.details && error.details.status === 404) {
    return <NotFound url={error.url}/>
  } else {
    return (
      <div>
        <h1>Error</h1>
        <p>
          {error.details && error.details.status && <span className="pr-1">{error.details.status}:</span>}
          {error.message ? error.message.toString() : error.toString()}.
        </p>
      </div>
    )
  }
}

export const NotFound = withRouter(({url, children, location}) => (
  <div>
    <h1>Page not found</h1>
    <p>The page <code>{url || location.pathname}</code> doesn't exist.</p>
    {children}
  </div>
))

export class Loading extends React.Component {
  constructor (props) {
    super(props)
    this.state = {dots: 0}
  }

  componentDidMount () {
    this.clear = setInterval(() => this.setState({dots: this.state.dots >= 3 ? 0 : this.state.dots + 1}), 500)
  }

  componentWillUnmount () {
    clearInterval(this.clear)
  }

  render () {
    return (
      <div className="loading text-muted">
        {this.props.message || 'loading'}{'.'.repeat(this.state.dots)}
        {this.props.children}
      </div>
    )
  }
}


export const Waiting = ({light, className}) => (
  <div className={`wait-circle${className ? ' ' + className : ''}`}>
    {[...Array(12).keys()].map(i => (
      <div key={i} className={`${light ? 'light' : 'dark'} el-${i}`}/>
    ))}
  </div>
)
