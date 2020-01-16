import React from 'react'
import {Button, Col, Row, UncontrolledTooltip} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext, Loading, confirm_modal} from 'reactstrap-toolbox'
import {Editor, empty_editor, from_markdown} from '../../Editor'
import Drop, {FileSummary} from '../../utils/Drop'
import Message from './Message'
import RightPanel from './RightPanel'
import Subject from './Subject'

const initial_state = {
  locked: false,
  files: [],
  new_message: empty_editor,
  comment: empty_editor,
  comment_parent: null,
  extra_prts: null,
  msg_modify_id: null,
  msg_modify_body: null,
}

const DropHelp = ({onClick}) => (
  <span className="text-muted">
    Drag and drop files, or click <a href="." onClick={onClick}>here</a> to select a file to attach.
  </span>
)

const DropSummary = ({files, locked, remove_file}) => (
  <div className="multi-previews">
    {files.map((file, i) => <FileSummary key={i} {...file} locked={locked} remove_file={remove_file}/>)}
  </div>
)

class ConvDetailsView extends React.Component {
  state = initial_state
  marked_seen = false

  async componentDidMount () {
    this.mounted = true
    this.update()
    this.remove_listener = window.logic.add_listener('change', this.update)
    document.addEventListener('keydown', this.on_keydown)
  }

  componentDidUpdate (prevProps, prevState) {
    const prev_msg_count = prevState.conv ? prevState.conv.messages.length : null
    if (prev_msg_count && this.state.conv && prev_msg_count < this.state.conv.messages.length) {
      window.scrollTo(0,document.body.scrollHeight)
    }
  }

  componentWillUnmount () {
    this.mounted = false
    this.remove_listener()
    document.removeEventListener('keydown', this.on_keydown)
  }

  setState (state, callback) {
    this.mounted && super.setState(state, callback)
  }

  on_keydown = e => {
    if (e.key === 'Enter' && e.ctrlKey) {
      if (this.state.new_message.has_changed) {
        this.add_msg()
      } else if (this.state.comment_parent) {
        this.add_comment()
      } else if (this.state.extra_prts) {
        this.add_participants()
      } else if (this.state.msg_modify_id) {
        this.msg_modify()
      }
    }
  }

  locked = part => {
    if (this.state.locked || this.state.conv.removed) {
      return true
    } else if (part === null) {
      return false
    } else if (part !== 'new_message' && this.state.new_message.has_changed) {
      return true
    } else if (part !== 'comment' && this.state.comment_parent) {
      return true
    } else if (part !== 'modify_msg' && this.state.msg_modify_id) {
      return true
    } else if (part !== 'extra_prts' && this.state.extra_prts) {
      return true
    }
    return false
  }

  update = async data => {
    // console.log('conversation update:', data)
    if (data && this.state.conv && data.conv !== this.state.conv.key) {
      // different conversation was updated, ignore
      return
    }
    if (data && data.new_key) {
      // conversation just got published and its key changed
      this.props.history.push(`/${data.new_key.substr(0, 10)}/`)
      return
    }

    let conv = await window.logic.conversations.get(this.props.match.params.key)
    if (!this.mounted) {
      return
    }
    if (!conv) {
      this.setState({not_found: true})
      return
    }
    this.props.ctx.setMenuItem(conv.primary_flag)
    this.props.ctx.setTitle(conv.subject)
    this.props.ctx.setConvTitle(conv.subject)
    this.setState({conv})
    this.update_contacts(conv.participants)
    if (this.pending_interaction && this.state.locked && this.pending_interaction === data.interaction) {
      this.pending_interaction = null
      this.last_action_id = data.last_action_id
      if (this.interaction_type === 'message:lock') {
        this.setState({locked: false})
      } else if (this.interaction_type !== 'subject:lock') {
        this.setState(initial_state)
      }
    }
    if (!this.marked_seen && this.state.conv) {
      this.marked_seen = true
      await window.logic.conversations.seen(this.state.conv.key)
    }
  }

  update_contacts = async p => {
    const participants = await window.logic.contacts.lookup_details(p)
    this.setState({conv: {...this.state.conv, participants}})
  }

  publish = async () => {
    if (!this.state.locked && !this.state.conv.published) {
      this.setState({locked: true})
      await window.logic.conversations.publish(this.state.conv.key)
    }
  }

  add_msg = async () => {
    if (!this.state.locked && !this.upload_ongoing() && this.state.new_message.has_changed) {
      await this.act({
        act: 'message:add',
        body: this.state.new_message.markdown,
        files: this.state.files.filter(f => f.done).map(f => f.file_id),
      })
    }
  }

  add_file = f => this.setState( s => ({files: [...s.files, f]}))

  remove_file = key => this.setState(s => ({files: s.files.filter(f => f.key !== key)}))

  update_file = (key, update) => (
    this.setState(s => ({files: s.files.map(f => f.key === key ? {...f, ...update} : f)}))
  )
  upload_ongoing = () => !!this.state.files.filter(f => f.progress).length

  add_comment = async () => {
    if (!this.state.locked && this.state.comment.has_changed && this.state.comment_parent) {
      await this.act({act: 'message:add', body: this.state.comment.markdown, parent: this.state.comment_parent})
    }
  }

  msg_modify_lock = async msg => {
    if (!this.state.locked && !this.state.msg_modify_id) {
      await this.act({act: 'message:lock', follows: msg.last_action})
      this.setState({msg_modify_id: msg.first_action, msg_modify_body: from_markdown(msg.body)})
    }
  }

  msg_modify_release = async () => {
    this.setState({msg_modify_id: null, msg_modify_body: null})
    await this.act({act: 'message:release', follows: this.last_action_id})
  }

  msg_modify = async () => {
    if (!this.state.locked && this.state.msg_modify_id && this.state.msg_modify_body.has_changed) {
      const action = {
        act: 'message:modify',
        body: this.state.msg_modify_body.markdown,
        follows: this.last_action_id,
      }
      await this.act(action)
    }
  }

  add_participants = async () => {
    if (!this.state.locked && this.state.extra_prts.length) {
      this.setState({locked: true})
      const actions = this.state.extra_prts.map(p => ({act: 'participant:add', participant: p.email}))
      this.pending_interaction = await window.logic.conversations.act(this.state.conv.key, actions)
    }
  }

  remove_participants = async prt => {
    if (!this.state.locked) {
      this.setState({locked: true})
      const ctx = {
        message: `Are you sure you want to remove ${prt.email} from this conversation?`,
        continue_text: 'Remove Participant',
      }
      if (await confirm_modal(ctx)) {
        await this.act({act: 'participant:remove', follows: prt.id, participant: prt.email})
      } else {
        this.setState({locked: false})
      }
    }
  }

  act = async (action, check_locked = false) => {
    if (check_locked && !this.state.locked) {
      console.warn('component already locked, cannot perform actions:', action)
      return
    }
    this.setState({locked: true})
    this.interaction_type = action.act
    this.pending_interaction = await window.logic.conversations.act(this.state.conv.key, [action])
  }

  lock_view = () => {
    if (this.state.locked) {
      throw Error('conversation already locked')
    }
    this.setState({locked: true})
    return () => this.setState({locked: false})
  }

  lock_subject = async () => {
    const follows = await window.logic.conversations.last_subject_action(this.state.conv.key)
    await this.act({act: 'subject:lock', follows})
  }
  release_subject = () => this.act({act: 'subject:release', follows: this.last_action_id}, true)
  set_subject = subject => this.act({act: 'subject:modify', body: subject, follows: this.last_action_id}, true)

  render () {
    if (this.state.not_found) {
      return (
        <div className="box">
          <h3>Conversation not found</h3>
          <p>Unable to find conversation <code>{this.props.match.params.key}</code>.</p>
        </div>
      )
    } else if (!this.state.conv || !this.props.ctx.user) {
      return <Loading/>
    }
    const new_message_locked = this.locked('new_message')
    const request_file_upload = (...args) => (
      window.logic.conversations.request_file_upload(this.state.conv.key, ...args)
    )
    return (
      <div>
        <Subject
          conv_state={this.state}
          publish={this.publish}
          lock_subject={this.lock_subject}
          lock_view={this.lock_view}
          set_subject={this.set_subject}
          release_subject={this.release_subject}
        />
        <div className="h5 mb-3">
          {this.state.conv.removed ? (
            <div>
              <span className="badge badge-dark mr-2 cursor-pointer" id="removed">Removed from Conversation</span>
              <UncontrolledTooltip placement="top" target="removed">
                You've been removed from this conversation, you can no longer contribute
                and will not see further updates.
              </UncontrolledTooltip>
            </div>
          ) : null}
        </div>
        <Row>
          <Col xl="4" className="order-xl-8">
            <RightPanel
              locked={part => this.locked(part)}
              state={this.state}
              add_participants={this.add_participants}
              remove_participants={this.remove_participants}
              set_participants={extra_prts => this.setState({extra_prts})}
            />
          </Col>
          <Col xl="8">
            {this.state.conv.messages.map(msg => (
              <Message msg={msg}
                       locked={part => this.locked(part)}
                       key={msg.first_action}
                       state={this.state}
                       session_id={this.props.ctx.user.session_id}
                       setState={s => this.setState(s)}
                       msg_modify={() => this.msg_modify()}
                       msg_modify_lock={() => this.msg_modify_lock(msg)}
                       msg_modify_release={() => this.msg_modify_release()}
                       add_comment={() => this.add_comment()}/>
            ))}
            <div className="box no-pad add-msg">
              <div className="border-bottom py-2">
                <b className="mr-1">Add Message</b>
                <span className="text-muted small">
                  Your message will go to everyone in this conversation.
                </span>
              </div>
              <div className="py-2">
                <Drop request_file_upload={request_file_upload}
                      help={DropHelp}
                      summary={DropSummary}
                      files={this.state.files}
                      locked={new_message_locked}
                      add_file={this.add_file}
                      remove_file={this.remove_file}
                      update_file={this.update_file}
                      maxSize={1024**3}>
                  <Editor
                    placeholder="reply to all..."
                    disabled={new_message_locked}
                    content={this.state.new_message}
                    onChange={value => this.setState({new_message: value})}
                  />
                </Drop>
                <div className="text-right">
                  <Button color="primary"
                          disabled={new_message_locked || this.upload_ongoing() || !this.state.new_message.has_changed}
                          onClick={this.add_msg}>
                    <FontAwesomeIcon icon={fas.faPaperPlane} className="mr-1"/>
                    {this.state.conv.draft ? 'Add Message' : 'Send'}
                  </Button>
                </div>
              </div>
            </div>
          </Col>
        </Row>
      </div>
    )
  }
}

export default withRouter(WithContext(ConvDetailsView))
