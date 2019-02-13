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

const post2iframe = msg => document.getElementById('login-iframe').contentWindow.postMessage(JSON.stringify(msg), '*')

function recaptcha_callback (grecaptcha_token) {
  post2iframe({grecaptcha_token})
}


class Login extends React.Component {
  constructor (props) {
    super(props)
    this.state = {error: null, recaptcha_shown: false}
    this.on_message = this.on_message.bind(this)
    this.authenticate = this.authenticate.bind(this)
  }

  async authenticate (data) {
    const user = await this.props.ctx.worker.call('auth-token', data)
    this.props.ctx.setUser(user)
    this.props.ctx.setMessage({icon: 'user', message: `Logged in successfully as ${user.name}`})
    this.props.history.replace(next_url(this.props.location) || '/')
  }

  async on_message (event) {
    if (event.origin !== 'null') {
      return
    }

    const data = JSON.parse(event.data)
    if (data.grecaptcha_required !== undefined) {
      if (data.grecaptcha_required && this.state.recaptcha_shown) {
        Recaptcha.reset()
      }
      this.setState({recaptcha_shown: data.grecaptcha_required})
      // this.props.ctx.setConnectionStatus(statuses.online_unauth_nodata)
    } else if (data.auth_token) {
      await this.authenticate(data)
    } else if (data.error) {
      console.log(data.error)
      this.props.ctx.setError(DetailedError(data.error.message, data.error.details))
    } else {
      throw DetailedError('unknown message from iframe', data)
    }
  }

  async componentDidMount () {
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
            <Recaptcha callback={recaptcha_callback}/>
          </Row>
        )}

        <Row className="justify-content-center">
          <Col xl="4" lg="6" md="8" className="login">
            <IFrame id="login-iframe" title="Login" src="/iframes/login.html"/>
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
