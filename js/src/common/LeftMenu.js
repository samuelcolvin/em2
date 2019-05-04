import React from 'react'
import {Link} from 'react-router-dom'
import {Row, Col, ListGroup, ListGroupItem as BsListGroupItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'


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
        <ListGroupItem tag={Link} to="/" active={s === 'inbox'} action>
          <FontAwesomeIcon icon={fas.faInbox} className="mr-1"/> Inbox
        </ListGroupItem>
        <ListGroupItem tag={Link} to="/sent/" active={s === 'sent'} action>
          <FontAwesomeIcon icon={fas.faPaperPlane} className="mr-1"/> Sent
        </ListGroupItem>
        <ListGroupItem tag={Link} to="/archive/" active={s === 'archive'} action>
          <FontAwesomeIcon icon={fas.faArchive} className="mr-1"/> Archive
        </ListGroupItem>
        <ListGroupItem tag={Link} to="/all/" active={s === 'all'} action>
          <FontAwesomeIcon icon={fas.faGlobe} className="mr-1"/> All
        </ListGroupItem>
        <ListGroupItem tag={Link} to="/spam/" active={s === 'spam'} action>
          <FontAwesomeIcon icon={fas.faMinusCircle} className="mr-1"/> Spam
        </ListGroupItem>
        <ListGroupItem tag={Link} to="/deleted/" active={s === 'deleted'} action>
          <FontAwesomeIcon icon={fas.faTrash} className="mr-1"/> Deleted
        </ListGroupItem>
      </ListGroup>
    </div>

    <div className="box no-pad">
      <ListGroup>
        <ListGroupItem tag={Link} to="/settings/" active={s === 'settings'} action>
          <FontAwesomeIcon icon={fas.faCog} className="mr-1"/> Settings
        </ListGroupItem>
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
