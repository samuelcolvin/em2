import React from 'react'
// import {Link} from 'react-router-dom'
import { Col, Row} from 'reactstrap'
import {Loading} from 'reactstrap-toolbox'
import {withRouter} from 'react-router-dom'
import {WithContext} from 'reactstrap-toolbox'
import {StatusDisplay} from './utils'

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

  render () {
    const c = this.state.contact
    if (!c) {
      return <Loading/>
    }
    const name = this.name(c)
    return (
      <div className="box pt-4">
        <Row>
          <Col md="4" className="text-right">
            <img src="/images/dft-user.png" className="contact" width="150" height="150" alt={name}/>
          </Col>
          <Col md="8">
            <h1 className="h3">{name}</h1>
            <div className="my-2">{c.c_strap_line || c.p_strap_line}</div>
            <div className="my-2">{c.email}</div>
            <div className="my-2"><StatusDisplay {...c}/> {c.profile_status_message}</div>

            {c.c_body ? (
              <div className="my-2">
                <div className="text-muted">Details:</div> {c.c_body}
              </div>
            ) : null}
            {c.p_body ? (
              <div className="my-2">
                <div className="text-muted">Profile Details:</div> {c.p_body}
              </div>
            ) : null}
            <code><pre className="text-muted">{JSON.stringify(c, null, 2)}</pre></code>
          </Col>
        </Row>
      </div>
    )
  }
}

// {
//   "id": 1,
//   "user_id": 4,
//   "email": "pear@example.com",
//   "c_profile_type": null,
//   "c_main_name": null,
//   "c_last_name": null,
//   "c_strap_line": null,
//   "c_image_url": null,
//   "contact_body": null,
//   "p_visibility": "public-searchable",
//   "p_profile_type": "personal",
//   "p_main_name": "Fred",
//   "p_last_name": "Jones",
//   "p_strap_line": null,
//   "p_image_url": null,
//   "p_body": null,
//   "profile_status": "dormant",
//   "profile_status_message": null
// }


export default withRouter(WithContext(DetailView))
