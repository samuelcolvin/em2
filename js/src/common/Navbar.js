import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {
  Collapse,
  Navbar as NavbarBootstrap,
  NavbarToggler,
  NavbarBrand,
  Nav,
  NavItem,
  NavLink,
} from 'reactstrap'
import {statuses} from '../lib'

const StatusBar = ({title, message, conn_status, user}) => {
  const class_name = ['extra-menu', 'fixed-top']
  // TODO replace connection_status_text with a symbol, eg. circle of different colour
  let connection_status_text
  if (conn_status === statuses.connecting) {
    // no connection status yet
    connection_status_text = 'connecting...'
    class_name.push('offline')
  } else if (conn_status === statuses.offline) {
    class_name.push('offline')
    connection_status_text = 'offline'
  } else {
    connection_status_text = 'online'
  }
  return (
    <div className={class_name.join(' ')}>
      <div className="container">
        <span>
          {title}
          {message && (
            <span className="ml-3 message">
              {message.icon && <FontAwesomeIcon icon={message.icon} className="mr-2"/>}
              {message.message || message.toString()}
            </span>
          )}
        </span>
        <span>
          {connection_status_text}
          {user && <span className="ml-2">{user.name}</span>}
        </span>
      </div>
    </div>
  )
}

export default class Navbar extends React.Component {
  constructor (props) {
    super(props)

    this.close = this.close.bind(this)
    this.state = {is_open: false}
  }

  close () {
    this.state.is_open && this.setState({is_open: false})
  }

  render () {
    return [
      <NavbarBootstrap key="1" color="light" light fixed="top" expand="md">
        <div className="container">
          <NavbarBrand tag={Link} onClick={this.close} to="/">
            em2
          </NavbarBrand>
          <NavbarToggler onClick={() => this.setState({is_open: !this.state.is_open})}/>
          <Collapse isOpen={this.state.is_open} navbar>
            <Nav navbar>
              {this.props.app_state.user && [
                <NavItem key="1" active={/^\/create\//.test(this.props.location.pathname)}>
                  <NavLink tag={Link} onClick={this.close} to="/create/">
                    Compose
                  </NavLink>
                </NavItem>,
              ]}
            </Nav>
            <form className="form-inline ml-auto">
              <input className="form-control" type="text" placeholder="Search"/>
            </form>
          </Collapse>
        </div>
      </NavbarBootstrap>,
      <StatusBar key="2" {...this.props.app_state}/>,
    ]
  }
}
