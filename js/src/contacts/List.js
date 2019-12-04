import React from 'react'
import {Link} from 'react-router-dom'
import {withRouter} from 'react-router-dom'
import {Button} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext} from 'reactstrap-toolbox'
import ListView from '../utils/List'
import {ContactImage, StatusDisplay} from './utils'

const ContactsList = ({items, ctx}) => items.map((c, i) => (
  // TODO show image
  <Link key={i} to={`/contacts/${c.id}/`} onClick={e => ctx.disable_nav && e.preventDefault()}>
    <div><ContactImage c={c}/></div>
    <div className="pl-3">{c.main_name} {c.last_name}</div>
    <div><StatusDisplay {...c}/></div>
    <div className="text-muted">{c.email}</div>
  </Link>
))

export default withRouter(WithContext(props => (
  <div>
    <div className="mb-2">
      <Button color="success" tag={Link} to="/contacts/create/">
        <FontAwesomeIcon icon={fas.faPlus} className="mr-1"/>New Contact
      </Button>
    </div>
    <ListView
      className="contacts-list"
      title="Contacts"
      menu_item="contacts"
      list_items={window.logic.contacts.list}
      render={ContactsList}
      none_text="No Contacts found"
      {...props}
    />
  </div>
)))
