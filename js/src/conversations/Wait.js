import React from 'react'
import {Redirect} from 'react-router-dom'
import {Loading} from 'reactstrap-toolbox'


export default ({match}) => {
  const [finished, set_finished] = React.useState(false)

  React.useEffect(() => {
    window.logic.conversations.wait_for(match.params.key).then(() => set_finished(true))
  }, [match.params.key])

  return finished ? <Redirect to={`/${match.params.key}/`}/> : <Loading/>
}
