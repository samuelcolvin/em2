import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {
  Collapse,
  Navbar as NavbarBootstrap,
  NavbarToggler,
  NavbarBrand,
  Nav,
  Tooltip,
  UncontrolledDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
} from 'reactstrap'
import {statuses} from '../utils/network'

const AccountSummary = ({conn_status, user, show_tooltip, toggle_tooltip}) => {
  let connection_status_text, connection_status_icon
  if (!conn_status || conn_status === statuses.connecting) {
    // no connection status yet
    connection_status_text = 'connecting...'
    connection_status_icon = 'spinner'
  } else if (conn_status === statuses.offline) {
    connection_status_text = 'offline'
    connection_status_icon = 'times'
  } else {
    connection_status_text = 'online'
    connection_status_icon = 'circle'
  }
  return (
    <span>
      <FontAwesomeIcon id="status-icon" icon={connection_status_icon}/>
      <Tooltip placement="bottom"
               isOpen={show_tooltip}
               trigger="hover"
               target="status-icon"
               delay={0}
               toggle={toggle_tooltip}>
        {connection_status_text}
      </Tooltip>
      {user && <span className="ml-2">{user.name}</span>}
    </span>
  )
}

export default class Navbar extends React.Component {
  constructor (props) {
    super(props)
    this.state = {is_open: false}
  }

  close = () => this.state.is_open && this.setState({is_open: false})

  toggle_tooltip = () => this.setState(s => ({show_tooltip: !s.show_tooltip}))

  render () {
    return (
      <NavbarBootstrap color="dark" dark fixed="top" expand="md">
        <div className="container">
          <NavbarToggler onClick={() => this.setState({is_open: !this.state.is_open})}/>
          {this.props.app_state.user && (
            <Collapse isOpen={this.state.is_open} navbar>
              <div className="d-flex width-full">
                <NavbarBrand tag={Link} onClick={this.close} to="/" className="width-third">
                  em2
                </NavbarBrand>
                <form className="form-inline ml-2 width-third">
                  <input id="search" className="form-control" type="text" placeholder="Search"/>
                </form>
                <Nav navbar className="width-third">
                  <UncontrolledDropdown nav inNavbar className="ml-auto">
                    <DropdownToggle nav caret>
                      <AccountSummary
                        {...this.props.app_state}
                        show_tooltip={this.state.show_tooltip}
                        toggle_tooltip={this.toggle_tooltip}
                      />
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
              </div>
            </Collapse>
          )}
        </div>
      </NavbarBootstrap>
    )
  }
}
