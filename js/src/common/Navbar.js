import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {
  Navbar as NavbarBootstrap,
  NavbarBrand,
  Nav,
  Tooltip,
  UncontrolledDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
} from 'reactstrap'
import {statuses} from '../utils/network'

const AccountSummary = ({conn_status, user}) => {
  const [show_tooltip, set_tooltip] = React.useState(false)

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
               toggle={() => set_tooltip(t => !t)}>
        {connection_status_text}
      </Tooltip>
      {user ? (
        <span className="ml-2">
          <span className="d-none d-sm-inline-block">
            {user.name}
            <FontAwesomeIcon icon="caret-down" className="ml-2"/>
          </span>
          <span className="d-inline-block d-sm-none">
            <span className="navbar-toggler-icon"/>
          </span>
        </span>
      ): null}
    </span>
  )
}

export default ({app_state}) => (
  <NavbarBootstrap color="dark" dark fixed="top" expand="md">
    <div className="container">
      {app_state.user ? (
        <div className="d-flex w-100">
          <NavbarBrand tag={Link} to="/" className="custom-nav-item d-none d-sm-block">
            em2
          </NavbarBrand>
          <form className="form-inline custom-nav-item flex-grow-1">
            <input id="search" className="form-control" type="text" placeholder="Search"/>
          </form>
          <Nav navbar className="custom-nav-item ml-2">
            <UncontrolledDropdown nav inNavbar className="ml-auto">
              <DropdownToggle nav>
                <AccountSummary {...app_state}/>
              </DropdownToggle>
              <DropdownMenu right className="navbar-dropdown">
                {app_state.other_sessions.map(s => (
                  <DropdownItem key={s.session_id} href={`/switch/${s.session_id}/`}
                                target="_blank">
                    Switch to <b>{s.name}</b>
                  </DropdownItem>
                ))}
                {app_state.other_sessions.length ? <DropdownItem divider/> : null}
                <DropdownItem href="/login/" target="_blank">
                  Login to another account
                </DropdownItem>
                <DropdownItem divider/>
                <DropdownItem tag={Link} to="/logout/">
                  Logout
                </DropdownItem>
              </DropdownMenu>
            </UncontrolledDropdown>
          </Nav>
        </div>
      ) : (
        <NavbarBrand tag={Link} to="/" className="w-33">
          em2
        </NavbarBrand>
      )}
    </div>
  </NavbarBootstrap>
)
