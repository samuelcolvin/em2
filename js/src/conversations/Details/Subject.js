import React from 'react'
import {Link} from 'react-router-dom'
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
import {WithContext, AsModal} from 'reactstrap-toolbox'


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

export default ({conv_state, publish, lock_subject, set_subject, release_subject}) => {
  const btns_disabled = Boolean(conv_state.locked || conv_state.comment_parent || conv_state.new_message)
  return (
    <div>
      <div className="box d-flex justify-content-between">
        <div className="align-self-center">
          <h2 className="conv-title">{conv_state.conv.subject}</h2>
        </div>
        <div>
          <ButtonGroup>
            {conv_state.conv.draft ? (
              <Button color="primary" disabled={btns_disabled} onClick={publish}>
                <FontAwesomeIcon icon={fas.faPaperPlane} className="mr-2"/> Publish
              </Button>
            ) : null}
            {conv_state.conv.inbox ? (
              <Button color="primary" disabled={btns_disabled}>
                <FontAwesomeIcon icon={fas.faArchive} className="mr-2"/> Archive
              </Button>
            ) : null}
            {conv_state.conv.restore ? (
              <Button color="success" disabled={btns_disabled}>
                <FontAwesomeIcon icon={fas.faTrash} className="mr-2"/>  Restore
              </Button>
            ) : (
              <Button color="warning" disabled={btns_disabled}>
                <FontAwesomeIcon icon={fas.faTrash} className="mr-2"/>  Delete
              </Button>
            )}
            {!(conv_state.conv.sent || conv_state.conv.draft || conv_state.conv.spam) ? (
              <Button color="danger" disabled={btns_disabled}>
                <FontAwesomeIcon icon={fas.faRadiation} className="mr-2"/> Spam
              </Button>
            ) : null}
            {conv_state.conv.spam ? (
              <Button color="success" disabled={btns_disabled}>
                <FontAwesomeIcon icon={fas.faRadiation} className="mr-2"/> Not Spam
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
}
