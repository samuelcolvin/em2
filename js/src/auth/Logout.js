import React from 'react'
import {Redirect} from 'react-router-dom'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {Loading, message_toast} from 'reactstrap-toolbox'


export default () => {
  const [finished, set_finished] = React.useState(false)

  React.useEffect(() => {
    window.logic.auth.logout().then(() => {
      message_toast({
        icon: fas.faUser,
        title: 'Logged out',
        message: 'Logged out successfully',
        progress: false,
        time: 2000,
      })
      // user gets redirected when the user gets set to null
      set_finished(true)
    })
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  return finished ? <Redirect to="/login/"/> : <Loading/>
}
