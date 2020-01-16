import React from 'react'
import {Link} from 'react-router-dom'
import {Col, Row, ButtonGroup, Button} from 'reactstrap'
import {Loading} from 'reactstrap-toolbox'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext, as_title} from 'reactstrap-toolbox'
import {MarkdownRenderer} from '../Editor'
import {StatusDisplay, ContactImage, contact_name} from './utils'


const Detail = ({name, showIf, children}) => {
  if (showIf === false || !children) {
    return null
  }
  return (
    <div className="my-2">
      <div className="small text-muted">{name}</div>
      <div className="pl-3">{children}</div>
    </div>
  )
}

class DetailView extends React.Component {
  state = {}

  componentDidMount () {
    this.update()
  }

  componentDidUpdate (prevProps) {
    if (this.props.location !== prevProps.location) {
      this.update()
    }
  }

  update = async () => {
    this.props.ctx.setMenuItem('contacts')
    const contact = await window.logic.contacts.details(this.props.match.params.id)
    if (contact) {
      this.setState({contact})
      this.props.ctx.setTitle(contact_name(contact))
    } else {
      this.setState({not_found: true})
    }
  }

  visibility_description = c => {
    switch(c.p_visibility) {
      case 'private':
        return (
          "This user has an em2 address with a profile which can only be seen once you've " +
          "received an an email from them"
        )
      case 'public':
        return "This user has an em2 address with a public profile which can only be accessed if you know their address"
      case 'public-searchable':
        return "This user has an em2 address with a public profile which can found by searching"
      default:
        return "This is an SMTP address no profile for the user is available"
    }
  }

  render () {
    if (this.state.not_found) {
      return <div>Contact not found.</div>
    }
    const c = this.state.contact
    if (!c) {
      return <Loading/>
    }
    const name = contact_name(c)
    return (
      <div className="box pt-3">
        <Row>
          <Col lg="4">
            <ContactImage c={c} size="large"/>
            <div className="mt-3 text-right">
              <ButtonGroup size="sm">
                <Button color="success" tag={Link} to={`/create/?participant=${encodeURI(c.email)}`}>
                  <FontAwesomeIcon icon={fas.faKeyboard} className="mr-1"/>Compose
                </Button>
                <Button color="primary" tag={Link} to={`/contacts/${c.id}/edit/`}>
                  <FontAwesomeIcon icon={fas.faEdit} className="mr-1"/>edit
                </Button>
              </ButtonGroup>
            </div>
          </Col>
          <Col lg="8">
            <h1 className="h3 pl-3">{name}</h1>
            <div className="my-2 pl-3">{c.c_strap_line || c.p_strap_line}</div>
            <div className="my-2 pl-3">
              <Link to={`/create/?participant=${encodeURI(c.email)}`}>{c.email}</Link>
            </div>
            <Detail name="Status" showIf={!!c.profile_status}>
              <StatusDisplay {...c}/> {c.profile_status_message}
            </Detail>

            <Detail name="Contact Type">{as_title(c.c_profile_type || c.p_profile_type || 'unknown')}</Detail>
            <Detail name="Visibility">
              {as_title(c.p_visibility || 'SMTP')}
              <div className="smaller text-muted small">({this.visibility_description(c)})</div>
            </Detail>
            <Detail name="Contact Details" showIf={!!c.c_details}><MarkdownRenderer value={c.c_details}/></Detail>
            <Detail name="Profile Details" showIf={!!c.p_details}><MarkdownRenderer value={c.p_details}/></Detail>
            {/*<code><pre className="text-muted">{JSON.stringify(c, null, 2)}</pre></code>*/}
            <i className="text-muted d-block mt-4">(TODO: show recent conversations)</i>
          </Col>
        </Row>
      </div>
    )
  }
}

export default withRouter(WithContext(DetailView))
