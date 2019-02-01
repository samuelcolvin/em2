import React from 'react'
import {Spinner} from 'reactstrap'
import {withRouter} from 'react-router-dom'

export const Error = ({error}) => {
  if (error.status === 404) {
    return <NotFound url={error.url}/>
  } else {
    return (
      <div className="box">
        <h1>Error</h1>
        <p>
          {error.status ? <span>{error.status}: </span> : ''}
          {error.message ? error.message : error.toString()}.
        </p>
      </div>
    )
  }
}

export const NotFound = withRouter(({url, children, location}) => (
  <div className="box">
    <h1>Page not found</h1>
    <p>The page <code>{url || location.pathname}</code> does not exist.</p>
    {children}
  </div>
))

export const Loading = ({className, children}) => (
  <div className={className || 'd-flex justify-content-center py-2'}>
    <Spinner color="info" />
    {children}
  </div>
)


export const Waiting = ({light, className}) => (
  <div className={`wait-circle${className ? ' ' + className : ''}`}>
    {[...Array(12).keys()].map(i => (
      <div key={i} className={`${light ? 'light' : 'dark'} el-${i}`}/>
    ))}
  </div>
)
