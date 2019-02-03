import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import ListView, {Paginate} from '../lib/retrieve/ListView'
import {format_ts} from '../lib'
import {Loading} from '../lib/Errors'

const ListConvs = ({state, get_page}) => {
  if (!state.items) {
    return <Loading/>
  } else if (state.items.length === 0) {
    return (
      <div key="f" className="text-muted text-center h5 mt-4">
        No Conversations found
      </div>
    )
  }
  // TODO include read notifications, popovers, use first name not addr
  return [
    <div key="l">
      {state.items.map((conv, i) => (
        <div key={i}>
          <Link to={`/${conv.key.substr(0, 10)}/`}>
            <span className="subject">{conv.subject}</span>
            <span className="body">
              {conv.snippet.email === 'props.user.email' ? '' : conv.snippet.addr + ':'} {conv.snippet.body}
            </span>

            <span className="float-right">
              <span className="icon">
                <FontAwesomeIcon icon="comment"/> {conv.snippet.msgs}
              </span>
              <span className="icon">
                <FontAwesomeIcon icon="users"/> {conv.snippet.prts}
              </span>
              <span>
                {format_ts(conv.updated_ts)}
              </span>
            </span>
          </Link>
        </div>
      ))}
    </div>,
    <Paginate key="p" pages={state['pages']} current_page={get_page()}/>,
  ]
}

export default () => (
  <div className="box conv-list">
    <ListView function={'list-conversations'} title="Conversations" Render={ListConvs}/>
  </div>
)
