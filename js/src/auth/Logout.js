import React from 'react'
import WithContext from '../lib/context'
import {Loading} from '../lib/Errors'

class Logout extends React.Component {
  async componentDidMount () {
    await this.props.ctx.worker.call('logout')
    this.props.ctx.setMessage({icon: 'user', message: 'Logged out successfully'})
    // user gets redirected when the user gets set to null
  }

  render () {
    return <Loading/>
  }
}
export default WithContext(Logout)
