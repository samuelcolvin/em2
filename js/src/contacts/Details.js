import React from 'react'
import {Link} from 'react-router-dom'
import { Col, Row, ButtonGroup, Button} from 'reactstrap'
import {Loading} from 'reactstrap-toolbox'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext, as_title} from 'reactstrap-toolbox'
import {StatusDisplay} from './utils'


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

const dft_icons = {
  work: fas.faUserTie,
  organisation: fas.faBuilding,
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
    this.setState({contact})
    this.props.ctx.setTitle(this.name(contact))
  }

  name = c => {
    if (c.c_main_name) {
      return `${c.c_main_name} ${c.c_last_name || ''}`.trim()
    } else if (c.p_main_name) {
      return `${c.p_main_name} ${c.p_last_name || ''}`.trim()
    } else {
      return c.email
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
    const c = this.state.contact
    if (!c) {
      return <Loading/>
    }
    const name = this.name(c)
    const image_url = c.c_image_url || c.p_image_url
    return (
      <div className="box pt-3">
        <Row>
          <Col lg="4">
            <div className="contact-image">
              {image_url ? (
                <img src={image_url} className="rounded" width="150" height="150" alt={name}/>
              ) : (
                <FontAwesomeIcon icon={dft_icons[c.p_profile_type] || fas.faUser} size="7x"/>
              )}
            </div>
            <div className="mt-3 text-right">
              <ButtonGroup size="sm">
                <Button color="success" tag={Link} to={`/create/?add=${encodeURI(c.email)}`}>
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
              <Link to={`/create/?add=${encodeURI(c.email)}`}>{c.email}</Link>
            </div>
            <Detail name="Status" showIf={!!c.profile_status}>
              <StatusDisplay {...c}/> {c.profile_status_message}
            </Detail>

            <Detail name="Contact Type">{as_title(c.c_profile_type || c.p_profile_type || 'unknown')}</Detail>
            <Detail name="Visibility">
              {as_title(c.p_visibility || 'SMTP')}
              <div className="smaller text-muted">({this.visibility_description(c)})</div>
            </Detail>
            <Detail name="Contact Details">{c.c_body}</Detail>
            <Detail name="Profile Details">{c.p_body}</Detail>
            {/*<code><pre className="text-muted">{JSON.stringify(c, null, 2)}</pre></code>*/}
          </Col>
        </Row>
        <i>(TODO: show recent conversations)</i>
      </div>
    )
  }
}


export default withRouter(WithContext(DetailView))
