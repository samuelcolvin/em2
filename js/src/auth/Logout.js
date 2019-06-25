import React from 'react'
import {Loading} from 'reactstrap-toolbox'


export default class Logout extends React.Component {
  componentDidMount() {
    window.logic.auth.logout()
  }

  render() {
    // redirect will be performed App when the user is set to none
    return <Loading/>
  }
}
