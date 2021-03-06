import React from 'react'
import {Row, Col, Button, FormFeedback} from 'reactstrap'
import {Link} from 'react-router-dom'
import {WithContext, DetailedError, Loading} from 'reactstrap-toolbox'
import {make_url} from '../logic/network'
import IFrame from './IFrame'
import Recaptcha from './Recaptcha'

function next_url (location) {
  const match = location.search.match('next=([^&]+)')
  const next = match ? decodeURIComponent(match[1]) : null
  return next === '/logout/' || next === null ? null : next
}


class Login extends React.Component {
  state = {error: null, recaptcha_shown: false, loading: false}
  iframe_ref = React.createRef()

  authenticate = async data => {
    this.setState({loading: true})
    await window.logic.auth.auth_token(data)
    this.props.history.replace(next_url(this.props.location) || '/')
  }

  on_message = async event => {
    if (event.origin !== 'null') {
      return
    }
    if (event.data.loaded) {
      const load_msg = {
        loaded: true,
        existing_sessions: await window.logic.session.all_emails(),
        login_url: make_url('auth', '/login/'),
      }
      this.iframe_ref.current.contentWindow.postMessage(load_msg, '*')
    } else if (event.data.grecaptcha_required !== undefined) {
      if (event.data.grecaptcha_required && this.state.recaptcha_shown) {
        Recaptcha.reset()
      }
      this.setState({recaptcha_shown: event.data.grecaptcha_required})
    } else if (event.data.auth_token) {
      await this.authenticate(event.data)
    } else if (event.data.error) {
      this.props.ctx.setError(DetailedError(event.data.error.message, event.data.error.details))
    } else {
      throw DetailedError('unknown message from iframe', event.data)
    }
  }

  recaptcha_callback = grecaptcha_token => (
    this.iframe_ref.current.contentWindow.postMessage({grecaptcha_token}, '*')
  )

  componentDidMount () {
    window.addEventListener('message', this.on_message)
    this.props.ctx.setTitle('Login')
  }

  componentWillUnmount () {
    window.removeEventListener('message', this.on_message)
  }

  set_session = async e => {
    if (!this.props.ctx.user) {
      // user not set, need to activate the session before following link
      e.preventDefault()
      await window.logic.session.init()
      this.props.history.push('/')
    }
  }

  render () {
    if (this.state.loading) {
       return <Loading/>
    }
    let head = (
      <div>
        Not yet a user? Go to <Link to="/signup/">Sign up</Link> to create an account.
      </div>
    )
    const next = next_url(this.props.location)
    if (next) {
      head = <div>Login to view <code>{next}</code>.</div>
    } else if (this.props.ctx.user || this.props.ctx.other_sessions.length) {
      const user = this.props.ctx.user || this.props.ctx.other_sessions[0]
      head = (
        <div>
          You're currently logged in as <b>{user.name} ({user.email})</b>,
          logging in again will create another session as a different user,
          <br/>
          or go to <Link to="/" onClick={this.set_session}>your dashboard</Link>.
        </div>
      )
    }
    return (
      <div>
        <Row className="justify-content-center">
          <Col lg="6">
            <div className="text-center">{head}</div>
          </Col>
        </Row>
        {this.state.error &&
          <div className="text-center mt-2">
            <FormFeedback className="d-block">{this.state.error}</FormFeedback>
          </div>
        }

        {this.state.recaptcha_shown && (
          <Row className="justify-content-center mt-4">
            <Recaptcha callback={this.recaptcha_callback}/>
          </Row>
        )}

        <Row className="justify-content-center">
          <Col xl="4" lg="6" md="8" className="login">
            <IFrame iframe_ref={this.iframe_ref}/>
          </Col>
        </Row>
        <div className="text-center">
          <Button tag={Link} to="/password-reset/" color="link" size="sm">Reset Password</Button>
        </div>
      </div>
    )
  }
}

export default WithContext(Login)
