import React from 'react'
import {Link, withRouter} from 'react-router-dom'
import {ListGroup, ListGroupItem as BsListGroupItem} from 'reactstrap'


const ListGroupItem = withRouter(({children, to, m, location}) => {
  m = m || RegExp('^' + to)
  console.log(m)
  return (
    <BsListGroupItem tag={Link} to={to} action active={m.test(location.pathname)}>
      {children}
    </BsListGroupItem>
  )
})


export default () => (
  <div>
    <div className="box no-pad">
      <ListGroup>
        <ListGroupItem tag={Link} to="/create/" action>Compose</ListGroupItem>
      </ListGroup>
    </div>

    <div className="box no-pad">
      <ListGroup>
        <ListGroupItem tag={Link} to="/" m={/^\/$/} action>All Conversations</ListGroupItem>
        <ListGroupItem tag={Link} to="/sent/" action>Sent</ListGroupItem>
        <ListGroupItem tag={Link} to="/spam/" action>Spam</ListGroupItem>
      </ListGroup>
    </div>

    <div className="box no-pad">
      <ListGroup>
        <ListGroupItem tag={Link} to="/settings/" action>Settings</ListGroupItem>
      </ListGroup>
    </div>
  </div>
)
