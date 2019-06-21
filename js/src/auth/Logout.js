import React from 'react'
import {Loading} from 'reactstrap-toolbox'


export default () => {
  React.useEffect(() => window.logic.auth.logout(), [])  // eslint-disable-line react-hooks/exhaustive-deps

  // redirect will be performed App when the user is set to none
  return <Loading/>
}
