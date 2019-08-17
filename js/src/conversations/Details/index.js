import React from 'react'
import {Button, Col, Row, UncontrolledTooltip} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext, Loading, confirm_modal} from 'reactstrap-toolbox'
import {Editor, empty_editor} from '../../Editor'
import Message from './Message'
import RightPanel from './RightPanel'
import Subject from './Subject'
import Drop from './Drop'


class ConvDetailsView extends React.Component {
  state = {files: [], new_message: empty_editor, comment: empty_editor}
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
      if (this.state.new_message.has_content) {
        this.add_msg()
      } else if (this.state.comment) {
        this.add_comment()
      } else if (this.state.extra_prts) {
        this.add_participants()
      }
    }
  }

  update = async data => {
    if (data && this.state.conv && data.conv !== this.state.conv.key) {
      // different conversation
    } else if (data && data.new_key) {
      this.props.history.push(`/${data.new_key.substr(0, 10)}/`)
    } else {
      let conv = await window.logic.conversations.get(this.props.match.params.key)
      if (!conv) {
        this.setState({not_found: true})
        return
      }
      if (!this.mounted) {
        return
      }
      this.props.ctx.setMenuItem(conv.primary_flag)
      this.props.ctx.setTitle(conv.subject)
      this.props.ctx.setConvTitle(conv.subject)
      this.setState({conv})
      if (this.action_ids && this.state.locked && this.action_ids.filter(id => conv.action_ids.has(id))) {
        this.action_ids = null
        this.setState({locked: false})
      }
      if (!this.marked_seen && this.state.conv) {
        this.marked_seen = true
        await window.logic.conversations.seen(this.state.conv.key)
      }
    }
  }

  publish = async () => {
    if (!this.state.locked && !this.state.conv.published) {
      this.setState({locked: true})
      await window.logic.conversations.publish(this.state.conv.key)
    }
  }

  add_msg = async () => {
    if (!this.state.locked && !this.upload_ongoing() && this.state.new_message.has_content) {
      this.setState({locked: true})
      const actions = [
        {
          act: 'message:add',
          body: this.state.new_message.to_markdown(),
          files: this.state.files.filter(f => f.done).map(f => f.content_id),
        },
      ]
      const r = await window.logic.conversations.act(this.state.conv.key, actions)
      this.action_ids = r.data.action_ids
      this.setState({new_message: empty_editor, files: []})
    }
  }

  add_file = f => this.setState( s => ({files: [...s.files, f]}))

  remove_file = key => this.setState(s => ({files: s.files.filter(f => f.key !== key)}))

  update_file = (key, update) => (
    this.setState(s => ({files: s.files.map(f => f.key === key ? {...f, ...update} : f)}))
  )
  upload_ongoing = () => !!this.state.files.filter(f => f.progress).length

  add_comment = async () => {
    if (!this.state.locked && this.state.comment.has_content && this.state.comment_parent) {
      this.setState({locked: true})
      const actions = [{act: 'message:add', body: this.state.comment.to_markdown(), parent: this.state.comment_parent}]
      const r = await window.logic.conversations.act(this.state.conv.key, actions)
      this.action_ids = r.data.action_ids
      this.setState({comment: empty_editor, comment_parent: null})
    }
  }

  add_participants = async () => {
    if (!this.state.locked && this.state.extra_prts.length) {
      this.setState({locked: true})
      const actions = this.state.extra_prts.map(p => (
        {act: 'participant:add', participant: p.email}
      ))
      const r = await window.logic.conversations.act(this.state.conv.key, actions)
      this.action_ids = r.data.action_ids
      this.setState({extra_prts: null})
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
        await this.act([{act: 'participant:remove', follows: prt.id, participant: prt.email}], true)
      } else {
        this.setState({locked: false})
      }
    }
  }

  act = async (actions, locked_ok) => {
    if (!this.state.locked || locked_ok) {
      this.setState({locked: true})
      const r = await window.logic.conversations.act(this.state.conv.key, actions)
      this.action_ids = r.data.action_ids
      return r.data.action_ids
    } else {
      console.warn('component already locked, cannot perform', actions)
    }
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
    const action_ids = await this.act([{act: 'subject:lock', follows}])
    return action_ids[0]
  }
  release_subject = follows => this.act([{act: 'subject:release', follows}])
  set_subject = (subject, follows) => this.act([{act: 'subject:modify', body: subject, follows}])

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
    const edit_locked = this.state.locked || this.state.conv.removed
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
          <Col xl="4 order-xl-8">
            <RightPanel
              edit_locked={edit_locked}
              state={this.state}
              add_participants={this.add_participants}
              remove_participants={this.remove_participants}
              set_participants={extra_prts => this.setState({extra_prts})}
            />
          </Col>
          <Col xl="8">
            {this.state.conv.messages.map(msg => (
              <Message msg={msg}
                       edit_locked={edit_locked}
                       key={msg.first_action}
                       state={this.state}
                       session_id={this.props.ctx.user.session_id}
                       setState={s => this.setState(s)}
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
                <Drop conv={this.state.conv.key}
                      files={this.state.files}
                      locked={edit_locked}
                      add_file={this.add_file}
                      remove_file={this.remove_file}
                      update_file={this.update_file}>
                  <Editor
                    placeholder="reply to all..."
                    disabled={!!(edit_locked || this.state.comment_parent || this.state.extra_prts)}
                    content={this.state.new_message}
                    onChange={value => this.setState({new_message: value})}
                  />
                </Drop>
                <div className="text-right">
                  <Button color="primary"
                          disabled={edit_locked || this.upload_ongoing() || !this.state.new_message.has_content}
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
