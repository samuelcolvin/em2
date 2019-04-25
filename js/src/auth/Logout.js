import React from 'react'
import {Redirect} from 'react-router-dom'
import {WithContext, Loading, message_toast} from 'reactstrap-toolbox'

class Logout extends React.Component {
  async componentDidMount () {
    await this.props.ctx.worker.call('logout')
    message_toast({
      icon: 'user',
      title: 'Logged out',
      message: 'Logged out successfully',
      progress: false,
      time: 2000,
    })
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
