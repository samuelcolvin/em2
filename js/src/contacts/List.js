import React from 'react'
import {Link} from 'react-router-dom'
import {withRouter} from 'react-router-dom'
import {WithContext} from 'reactstrap-toolbox'
import ListView from '../utils/List'
import {StatusDisplay} from './utils'

const ContactsList = ({items, ctx}) => items.map((c, i) => (
  // TODO show image
  <Link key={i} to={`/contacts/${c.id}/`} onClick={e => ctx.disable_nav && e.preventDefault()}>
    <div>{c.main_name} {c.last_name}</div>
    <div><StatusDisplay {...c}/></div>
    <div className="text-muted">{c.email}</div>
  </Link>
))

export default withRouter(WithContext(props => (
  <ListView
    className="contacts-list"
    title="Contacts"
    menu_item="contacts"
    list_items={window.logic.contacts.list}
    render={ContactsList}
    none_text="No Contacts found"
    {...props}
  />
)))
