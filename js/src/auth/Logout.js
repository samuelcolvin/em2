import React from 'react'
import {Redirect} from 'react-router-dom'
import {WithContext, Loading} from 'reactstrap-toolbox'

class Logout extends React.Component {
  async componentDidMount () {
    await this.props.ctx.worker.call('logout')
    this.props.ctx.setMessage({icon: 'user', message: 'Logged out successfully'})
    // user gets redirected when the user gets set to null
    this.setState({finished: true})
  }

  render () {
    if (this.state && this.state.finished) {
      return <Redirect to="/login/"/>
    } else {
      return <Loading/>
    }
  }
}
export default WithContext(Logout)
