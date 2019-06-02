import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {
  Navbar as NavbarBootstrap,
  NavbarBrand,
  Nav,
  Tooltip,
  UncontrolledDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
  Row,
  Col,
} from 'reactstrap'
import {statuses} from './logic/network'
import Search from './Search'

const AccountSummary = ({conn_status, user}) => {
  const [show_tooltip, set_tooltip] = React.useState(false)

  let connection_status_text, connection_status_icon
  if (!conn_status || conn_status === statuses.connecting) {
    // no connection status yet
    connection_status_text = 'connecting...'
    connection_status_icon = fas.faSpinner
  } else if (conn_status === statuses.offline) {
    connection_status_text = 'offline'
    connection_status_icon = fas.faTimes
  } else if (conn_status === statuses.problem) {
    connection_status_text = 'connection problems'
    connection_status_icon = fas.faMinusCircle
  } else {
    connection_status_text = 'online'
    connection_status_icon = fas.faCircle
  }
  return (
    <span>
      <FontAwesomeIcon id="status-icon" icon={connection_status_icon}/>
      <Tooltip placement="left"
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
            <FontAwesomeIcon icon={fas.faCaretDown} className="ml-2"/>
          </span>
          <span className="d-inline-block d-sm-none">
            <span className="navbar-toggler-icon"/>
          </span>
        </span>
      ): null}
    </span>
  )
}

const NavbarUser = ({app_state}) => (
  <div className="d-flex w-100">
    <NavbarBrand tag={Link} to="/" className="custom-nav-item d-none d-sm-block">
      em2
    </NavbarBrand>
    <form className="form-inline custom-nav-item flex-grow-1">
      {/*<input id="search" className="form-control" type="text" placeholder="Search"/>*/}
      <Search/>
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
)

const StatusBar = ({conn_status, conv_title}) => {
  const scroll_threshold = 50
  const [down_page, set_down_page] = React.useState(false)

  const on_scroll = () => {
    const scroll_y = window.scrollY
    if (!down_page && scroll_y > scroll_threshold) {
      set_down_page(true)
    } else if (down_page && scroll_y <= scroll_threshold) {
      set_down_page(false)
    }
  }

  React.useEffect(() => {
    on_scroll()
    window.addEventListener('scroll', on_scroll)
    return () => window.removeEventListener('scroll', on_scroll)
  })

  const error_msg = {
    [statuses.problem]: 'Connection Problems',
    [statuses.offline]: 'Offline',
  }[conn_status] || null
  const show = (down_page && conv_title) || error_msg

  return (
    <div className={`status-bar${show ? ' show' : ''} ${error_msg ? 'bg-danger' : 'bg-primary'}`}>
      <div className="container h-100">
        <Row className="align-items-center h-100">
          <Col md="3"/>
          <Col md="6">
            {conv_title}
          </Col>
          <Col md="3" className="text-right">
            {error_msg || (conv_title ? null : 'Online')}
          </Col>
        </Row>
      </div>
    </div>
  )
}

export default ({app_state}) => ([
  <NavbarBootstrap key="nb" color="dark" dark fixed="top" expand="md">
    <div className="container">
      {app_state.user ? <NavbarUser app_state={app_state}/> : <NavbarBrand tag={Link} to="/">em2</NavbarBrand>}
    </div>
  </NavbarBootstrap>,
  <StatusBar key="status" {...app_state}/>,
])
