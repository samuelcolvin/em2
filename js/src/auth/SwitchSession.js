import React from 'react'
import {Redirect} from 'react-router-dom'
import {WithContext, Loading} from 'reactstrap-toolbox'

class SwitchSession extends React.Component {
  async componentDidMount () {
    const session_id = parseInt(this.props.match.params.id)
    const session = await this.props.ctx.worker.call('switch', session_id)
    console.log(session)
    this.props.ctx.setMessage({icon: 'user', message: `Switched Session to ${session.name}`})
    this.setState({finished: true})
  }

  render () {
    if (this.state && this.state.finished) {
      return <Redirect to="/"/>
    } else {
      return <Loading/>
    }
  }
}
export default WithContext(SwitchSession)
