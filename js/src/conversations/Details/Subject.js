import React from 'react'
import {Link, withRouter} from 'react-router-dom'
import {
  InputGroup,
  Input,
  InputGroupAddon,
  Button,
  FormFeedback,
  ButtonGroup,
  UncontrolledButtonDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext, AsModal, message_toast} from 'reactstrap-toolbox'


class EditSubject_ extends React.Component {
  constructor (props) {
    super(props)
    this.state = {subject: this.props.subject, error: null}
    this.unregister = this.props.register_change_handler(this.on_toggle)
    this.follows_id = null
  }

  on_toggle = e => {
    if (!e.shown && this.follows_id) {
      this.props.release_subject(this.follows_id)
    }
  }

  componentWillUnmount () {
    this.unregister()
  }

  async componentDidMount () {
    this.follows_id = await this.props.lock_subject()
  }

  submit = async e => {
    e.preventDefault()
    if (this.state.subject === this.props.subject) {
      this.setState({error: 'Subject unchanged'})
    } else  {
      await this.props.set_subject(this.state.subject, this.follows_id)
      this.props.done()
    }
  }

  render () {
    return (
      <form className={this.props.form_body_class} onSubmit={this.submit}>
        <InputGroup>
          <Input
            invalid={Boolean(this.state.error)}
            placeholder="new subject..." required
            value={this.state.subject}
            onChange={e => this.setState({subject: e.target.value, error: null})}
          />
          <InputGroupAddon addonType="append">
            <Button color="primary" type="submit">
              Save
            </Button>
          </InputGroupAddon>
        </InputGroup>
        {this.state.error && <FormFeedback className="d-block">{this.state.error}</FormFeedback>}
      </form>
    )
  }
}

const EditSubject = AsModal(WithContext(EditSubject_))

const msg_lookup = {
  archive: 'Archived',
  delete: 'Deleted',
  restore: 'Restored',
  spam: 'Spam',
  ham: 'Not Spam',
}

export default withRouter(({history, conv_state, publish, lock_subject, set_subject, release_subject}) => {
  const btns_disabled = Boolean(conv_state.locked || conv_state.comment_parent || conv_state.new_message)
  const set_flag = (flag, leave=true) => {
    window.logic.conversations.set_flag(conv_state.conv.key, flag)
    message_toast({
      icon: fas.faEnvelope,
      title: msg_lookup[flag],
      message: conv_state.conv.subject,
      progress: false,
      time: 3000,
    })
    if (leave) {
      const f = conv_state.conv.primary_flag
      history.push(f === 'inbox' ? '/' : `/${f}/`)
    }
  }
  return (
    <div className="conv-subject">
      <div className="box d-flex justify-content-between flex-wrap">
        <div className="align-self-center">
          <h2 className="conv-title">{conv_state.conv.subject}</h2>
        </div>
        <div>
          <ButtonGroup>
            {conv_state.conv.draft ? (
              <Button color="primary" disabled={btns_disabled} onClick={publish}>
                <FontAwesomeIcon icon={fas.faPaperPlane} className="icon"/> Publish
              </Button>
            ) : null}
            {conv_state.conv.inbox ? (
              <Button color="primary" disabled={btns_disabled} onClick={() => set_flag('archive')}>
                <FontAwesomeIcon icon={fas.faArchive} className="icon"/> Archive
              </Button>
            ) : null}
            {conv_state.conv.deleted ? (
              <Button color="success" disabled={btns_disabled} onClick={() => set_flag('restore', false)}>
                <FontAwesomeIcon icon={fas.faTrash} className="icon"/>  Restore
              </Button>
            ) : (
              <Button color="warning" disabled={btns_disabled} onClick={() => set_flag('delete')}>
                <FontAwesomeIcon icon={fas.faTrash} className="icon"/>  Delete
              </Button>
            )}
            {!(conv_state.conv.sent || conv_state.conv.draft || conv_state.conv.spam) ? (
              <Button color="danger" disabled={btns_disabled} onClick={() => set_flag('spam')}>
                <FontAwesomeIcon icon={fas.faRadiation} className="icon"/> Spam
              </Button>
            ) : null}
            {conv_state.conv.spam ? (
              <Button color="success" disabled={btns_disabled} onClick={() => set_flag('ham', false)}>
                <FontAwesomeIcon icon={fas.faRadiation} className="icon"/> Not Spam
              </Button>
            ) : null}

            <UncontrolledButtonDropdown>
              <DropdownToggle caret>
                More
              </DropdownToggle>
              <DropdownMenu right>
                <DropdownItem  tag={Link} to="./edit-subject/" disabled={btns_disabled}>
                  Edit Subject
                </DropdownItem>
              </DropdownMenu>
            </UncontrolledButtonDropdown>
          </ButtonGroup>
        </div>
    </div>

    <EditSubject
      subject={conv_state.conv.subject}
      set_subject={set_subject}
      lock_subject={lock_subject}
      release_subject={release_subject}
      title="Edit Subject"
      regex={/edit-subject\/$/}
      className="simplified-modal"
    />
    </div>
  )
})
