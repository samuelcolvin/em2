import React from 'react'
import {Link} from 'react-router-dom'
import {Row, Col, ListGroup, ListGroupItem as BsListGroupItem} from 'reactstrap'


const ListGroupItem = ({children, to, active}) => (
  <BsListGroupItem tag={Link} to={to} action active={active}>
    {children}
  </BsListGroupItem>
)

const LeftMenu = ({s}) => (
  <div>
    <div className="box no-pad">
      <ListGroup>
        <ListGroupItem tag={Link} to="/create/" active={s === 'create'} action>Compose</ListGroupItem>
      </ListGroup>
    </div>

    <div className="box no-pad">
      <ListGroup>
        <ListGroupItem tag={Link} to="/" active={s === 'all'} action>All Conversations</ListGroupItem>
        <ListGroupItem tag={Link} to="/sent/" active={s === 'sent'} action>Sent</ListGroupItem>
        <ListGroupItem tag={Link} to="/spam/" active={s === 'spam'} action>Spam</ListGroupItem>
      </ListGroup>
    </div>

    <div className="box no-pad">
      <ListGroup>
        <ListGroupItem tag={Link} to="/settings/" active={s === 'settings'} action>Settings</ListGroupItem>
      </ListGroup>
    </div>
  </div>
)

export default (WrappedComponent, selected) => {
  return props => (
    <Row>
      <Col md="3"><LeftMenu s={selected}/></Col>
      <Col md="9"><WrappedComponent {...props}/></Col>
    </Row>
  )
}
