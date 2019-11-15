import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {withRouter} from 'react-router-dom'
import {WithContext} from 'reactstrap-toolbox'
import {format_ts} from '../utils/dt'
import ListView from '../utils/List'

export const ConvList = ({items, ctx}) => items.map((conv, i) => (
  <Link key={i} to={`/${conv.key.substr(0, 10)}/`} className={conv.seen ? 'muted' : ''}
        onClick={e => ctx.disable_nav && e.preventDefault()}>
    <div>{conv.details.sub}</div>
    <div className="summary">
      <span className="body">
        {conv.details.email === (ctx.user && ctx.user.email) ? 'you' : conv.details.email}: {conv.details.prev}
      </span>
    </div>

    <div className="details">
      <span className="d-none d-lg-inline-block">
        <span className="icon">
          <FontAwesomeIcon icon={fas.faComment}/> {conv.details.msgs}
        </span>
        <span className="icon">
          <FontAwesomeIcon icon={fas.faUsers}/> {conv.details.prts}
        </span>
      </span>
      <span>
        {format_ts(conv.updated_ts)}
      </span>
    </div>
  </Link>
))

const ConvListView = props => {
  const flag = props.match.params.flag || 'inbox'
  const list_items = async page => (
    {
      items: await window.logic.conversations.list({page, flag}),
      pages: window.logic.conversations.pages(flag),
    }
  )
  return (
    <ListView
      className="conv-list"
      title={props.ctx.user.name}
      menu_item={flag}
      list_items={list_items}
      render={ConvList}
      none_text="No Conversations found"
      {...props}
    />
  )
}

export default withRouter(WithContext(ConvListView))
