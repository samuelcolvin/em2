import React from 'react'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {Loading, message_toast} from 'reactstrap-toolbox'


export default () => {
  React.useEffect(() => {
    window.logic.auth.logout().then(() => {
      message_toast({
        icon: fas.faUser,
        title: 'Logged out',
        message: 'Logged out successfully',
        progress: false,
        time: 2000,
      })
    })
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // redirect will be performed App when the user is set to none
  return <Loading/>
}
