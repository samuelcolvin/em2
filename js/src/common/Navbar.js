import React from 'react'
import {Link} from 'react-router-dom'
import {
  Collapse,
  Navbar as NavbarBootstrap,
  NavbarToggler,
  NavbarBrand,
  Nav,
  NavItem,
  NavLink,
} from 'reactstrap'

const Status = ({title, message, status, user}) => {
  const class_name = ['extra-menu', 'fixed-top']
  let nav_status
  if (user) {
    // online
    nav_status = ''
  } else if (status) {
    class_name.push('anon')
    nav_status = 'not authenticated'
  } else {
    class_name.push('offline')
    nav_status = 'offline'
  }
  return (
    <div className={class_name.join(' ')}>
      <div className="container">
        <span>
          {title}
          {message && <span className="ml-2">TODO format {message}</span>}
        </span>
        <span>
          {nav_status}
          {user && <span className="ml-2">{user.address}</span>}
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
      <NavbarBootstrap key="1" color="light" fixed="top" expand="md">
        <div className="container">
          <NavbarBrand tag={Link} onClick={this.close} to="/">
            em2
          </NavbarBrand>
          <NavbarToggler onClick={() => this.setState({is_open: !this.state.is_open})}/>
          <Collapse isOpen={this.state.is_open} navbar>
            <Nav className="ml-auto" navbar>
              {this.props.user && [
                <NavItem key="1" active={/^\/create\//.test(this.props.location.pathname)}>
                  <NavLink tag={Link} onClick={this.close} to="/create/">
                    Create Conversation
                  </NavLink>
                </NavItem>
              ]}
            </Nav>
          </Collapse>
        </div>
      </NavbarBootstrap>,
      <Status key="2" {...this.props}/>,
    ]
  }
}
