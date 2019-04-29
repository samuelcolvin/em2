import React from 'react'
import {Redirect} from 'react-router-dom'
import {WithContext, Loading, message_toast} from 'reactstrap-toolbox'


const Logout = ({ctx}) => {
  const [finished, set_finished] = React.useState(false)

  React.useEffect(() => {
    ctx.worker.call('logout').then(() => {
      message_toast({
        icon: 'user',
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

export default WithContext(Logout)
