import React from 'react'
// import {Link} from 'react-router-dom'
// import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import DetailView from '../lib/retrieve/DetailView'
// import {format_ts} from '../lib'
import {Loading} from '../lib/Errors'

const ConvDetail = ({state}) => {
  // console.log(state)
  if (!state.actions) {
    return <Loading/>
  }
  return (
    <div>
      TODO
      {state.actions.map((a, i) => (
        <div className="box" key={i}>
          <pre>{JSON.stringify(a, null, 2)}</pre>
        </div>
      ))}
    </div>
  )
}

export default () => (
  <DetailView function={'get-conversation'} title="Conversation" Render={ConvDetail}/>
)
