import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {withRouter} from 'react-router-dom'
import {WithContext} from 'reactstrap-toolbox'
import ListView from '../utils/List'

const _status = (className, text, icon) => (
  <span className={className}>{text} <FontAwesomeIcon WixedWidth icon={icon}/></span>
)

const status_display = profile_status => {
  if (profile_status === 'active') {
    return _status('text-info', 'Active', fas.faComment)
  } else if (profile_status === 'away') {
    return _status('text-secondary', 'Away', fas.faPlaneDeparture)
  } else if (profile_status === 'dormant') {
    return _status('text-danger', 'Dormant', fas.faMinusCircle)
  }
}

const is_muted = c => c.profile_status === 'away' || c.profile_status === 'dormant'

const ContactsList = ({items, ctx}) => items.map((c, i) => (
  // TODO show image
  <Link key={i} to={`/contacts/${c.id}/`} className={is_muted(c) ? 'muted' : ''}
        onClick={e => ctx.disable_nav && e.preventDefault()}>
    <div>{c.main_name} {c.last_name}</div>
    <div>{status_display(c.profile_status)}</div>
    <div className="text-muted">{c.email}</div>
  </Link>
))

const ContactsListView = props => {
  return (
    <ListView
      className="contacts-list"
      title="Contacts"
      menu_item="contacts"
      list_items={window.logic.contacts.list}
      render={ContactsList}
      none_text="No Contacts found"
      {...props}
    />
  )
}

export default withRouter(WithContext(ContactsListView))
