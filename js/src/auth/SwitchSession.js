import React from 'react'
import {Redirect} from 'react-router-dom'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {Loading, message_toast} from 'reactstrap-toolbox'

export default class SwitchSession extends React.Component {
  async componentDidMount () {
    const session_id = parseInt(this.props.match.params.id)
    const session = await window.logic.session.switch(session_id)
    message_toast({icon: fas.faUser, title: 'Switched Session', message: `Switched Session to ${session.name}`})
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
