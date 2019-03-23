import React from 'react'
import {Link, withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {
  Collapse,
  Navbar as NavbarBootstrap,
  NavbarToggler,
  NavbarBrand,
  Nav,
  NavItem,
  NavLink,
  Tooltip,
  UncontrolledDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
} from 'reactstrap'
import {statuses} from '../lib'

const StatusBar = ({title, message, conn_status, user, show_tooltip, toggle_tooltip}) => {
  const class_name = ['extra-menu', 'fixed-top']
  let connection_status_text, connection_status_icon
  if (!conn_status || conn_status === statuses.connecting) {
    // no connection status yet
    connection_status_text = 'connecting...'
    connection_status_icon = 'spinner'
    class_name.push('connecting')
  } else if (conn_status === statuses.offline) {
    class_name.push('offline')
    connection_status_text = 'offline'
    connection_status_icon = 'times'
  } else {
    connection_status_text = 'online'
    connection_status_icon = 'circle'
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
          <FontAwesomeIcon id="status-icon" icon={connection_status_icon}/>
          <Tooltip placement="top" isOpen={show_tooltip}
                   trigger="hover"
                   target="status-icon"
                   delay={0}
                   toggle={toggle_tooltip}>
            {connection_status_text}
          </Tooltip>
          {user && <span className="ml-2">{user.name}</span>}
        </span>
      </div>
    </div>
  )
}

const NavButton = withRouter(({children, path, close, location}) => (
  <NavItem active={RegExp('^' + path).test(location.pathname)}>
    <NavLink tag={Link} onClick={close} to={path}>
      {children}
    </NavLink>
  </NavItem>
))

export default class Navbar extends React.Component {
  constructor (props) {
    super(props)
    this.state = {is_open: false}
  }

  close = () => this.state.is_open && this.setState({is_open: false})

  toggle_tooltip = () => this.setState(s => ({show_tooltip: !s.show_tooltip}))

  render () {
    return [
      <NavbarBootstrap key="1" color="light" light fixed="top" expand="md">
        <div className="container">
          <NavbarBrand tag={Link} onClick={this.close} to="/">
            em2
          </NavbarBrand>
          <NavbarToggler onClick={() => this.setState({is_open: !this.state.is_open})}/>
          {this.props.app_state.user && (
            <Collapse isOpen={this.state.is_open} navbar>
              <Nav navbar>
                <NavButton key="create" path="/create/" close={this.close}>Compose</NavButton>
              </Nav>
              <div className="flex-fill"/>
              <Nav navbar>
                <NavButton key="settings" path="/settings/" close={this.close}>Settings</NavButton>
                <UncontrolledDropdown nav inNavbar>
                  <DropdownToggle nav caret>
                    Account
                  </DropdownToggle>
                  <DropdownMenu right>
                    {this.props.app_state.other_sessions.map(s => (
                      <DropdownItem key={s.session_id} onClick={this.close} href={`/switch/${s.session_id}/`}
                                    target="_blank">
                        Switch to <b>{s.name}</b>
                      </DropdownItem>
                    ))}
                    {this.props.app_state.other_sessions.length ? <DropdownItem divider/> : null}
                    <DropdownItem onClick={this.close} href="/login/" target="_blank">
                      Login to another account
                    </DropdownItem>
                    <DropdownItem divider/>
                    <DropdownItem tag={Link} onClick={this.close} to="/logout/">
                      Logout
                    </DropdownItem>
                  </DropdownMenu>
                </UncontrolledDropdown>
              </Nav>
              <form className="form-inline ml-2">
                <input className="form-control" type="text" placeholder="Search"/>
              </form>
            </Collapse>
          )}
        </div>
      </NavbarBootstrap>,
      <StatusBar
        key="2"
        {...this.props.app_state}
        show_tooltip={this.state.show_tooltip}
        toggle_tooltip={this.toggle_tooltip}
      />,
    ]
  }
}
