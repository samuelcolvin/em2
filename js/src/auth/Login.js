import React from 'react'
import {Row, Col, Button, FormFeedback} from 'reactstrap'
import {Link} from 'react-router-dom'
import WithContext from '../lib/context'
import IFrame from './IFrame'
import Recaptcha from './Recaptcha'
import {DetailedError} from '../lib'

function next_url (location) {
  const match = location.search.match('next=([^&]+)')
  const next = match ? decodeURIComponent(match[1]) : null
  return next === '/logout/' || next === null ? null : next
}


class Login extends React.Component {
  state = {error: null, recaptcha_shown: false}
  iframe_ref = React.createRef()

  authenticate = async data => {
    const user = await this.props.ctx.worker.call('auth-token', data)
    this.props.ctx.setUser(user)
    this.props.ctx.setMessage({icon: 'user', message: `Logged in successfully as ${user.name}`})
    this.props.history.replace(next_url(this.props.location) || '/')
  }

  on_message = async event => {
    if (event.origin !== 'null') {
      return
    }
    if (event.data.grecaptcha_required !== undefined) {
      if (event.data.grecaptcha_required && this.state.recaptcha_shown) {
        Recaptcha.reset()
      }
      this.setState({recaptcha_shown: event.data.grecaptcha_required})
    } else if (event.data.auth_token) {
      await this.authenticate(event.data)
    } else if (event.data.error) {
      console.log(event.data.error)
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
    this.props.ctx.setUser(null)
    this.props.ctx.setTitle('Login')
  }

  componentWillUnmount () {
    window.removeEventListener('message', this.on_message)
  }

  render () {
    const next = next_url(this.props.location)
    return (
      <div>
        <Row className="justify-content-center">
          <Col lg="6">
            {next ?
              <div className="text-center">
                Login to view <code>{next}</code>.
              </div>
              :
              <div className="text-center">
                Not yet a user? Go to <Link to="/signup/">Sign up</Link> to create an account.
              </div>
            }
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
