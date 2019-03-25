import React from 'react'
import {Button, ButtonGroup, Col, Row} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {sleep} from '../../lib'
import {Loading} from '../../lib/Errors'
import WithContext from '../../lib/context'
import Message from './Message'
import RightPanel from './RightPanel'
import EditSubject from './EditSubject'

const DraftButtons = ({state, add_msg, publish}) => (
  <ButtonGroup>
    <Button color="secondary" disabled={state.locked || !state.new_message} onClick={add_msg}>
      Add Message
    </Button>
    <Button color="primary" disabled={state.locked || !!state.new_message} onClick={publish}>
      <FontAwesomeIcon icon="paper-plane" className="mr-1"/>
      Publish
    </Button>
  </ButtonGroup>
)

const PublishedButtons = ({state, add_msg}) => (
  <Button color="primary" disabled={state.locked || !state.new_message} onClick={add_msg}>
    <FontAwesomeIcon icon="paper-plane" className="mr-1"/>
    Send
  </Button>
)

class ConvDetailsView extends React.Component {
  state = {}
  comment_ref = React.createRef()

  async componentDidMount () {
    this.mounted = true
    this.update()
    this.remove_listener = this.props.ctx.worker.add_listener('change', this.update)
    document.addEventListener('keydown', this.on_keydown)
    await sleep(1000)
    if (this.mounted) {
      await this.props.ctx.worker.call('seen', {conv: this.state.conv.key})
    }
  }

  componentDidUpdate (prevProps, prevState) {
    if (this.props.match.params.key !== prevProps.match.params.key) {
      // moved to a new conversation, clear the state completely
      this.setState(Object.assign(...Object.keys(this.state).map(k => ({[k]: null}))))
      this.update()
    } else {
      const prev_msg_count = prevState.conv ? prevState.conv.messages.length : null
      if (prev_msg_count && this.state.conv && prev_msg_count < this.state.conv.messages.length) {
        window.scrollTo(0,document.body.scrollHeight)
      }
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
      if (this.state.new_message) {
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
      const conv = await this.props.ctx.worker.call('get-conversation', this.props.match.params)
      this.props.ctx.setTitle(conv.subject)
      this.setState({conv})
      if (this.action_ids && this.state.locked && this.action_ids.filter(id => conv.action_ids.has(id))) {
        this.action_ids = null
        this.setState({locked: false})
      }
    }
  }

  publish = async () => {
    if (!this.state.locked && !this.state.conv.published) {
      this.setState({locked: true})
      await this.props.ctx.worker.call('publish', {conv: this.state.conv.key})
    }
  }

  add_msg = async () => {
    if (!this.state.locked && this.state.new_message) {
      this.setState({locked: true})
      const actions = [{act: 'message:add', body: this.state.new_message}]
      const r = await this.props.ctx.worker.call('act', {conv: this.state.conv.key, actions})
      this.action_ids = r.data.action_ids
      this.setState({new_message: null})
    }
  }

  add_comment = async () => {
    if (!this.state.locked && this.state.comment && this.state.comment_parent) {
      this.setState({locked: true})
      const actions = [{act: 'message:add', body: this.state.comment, parent: this.state.comment_parent}]
      const r = await this.props.ctx.worker.call('act', {conv: this.state.conv.key, actions})
      this.action_ids = r.data.action_ids
      this.setState({comment: null, comment_parent: null})
    }
  }

  add_participants = async () => {
    if (!this.state.locked && this.state.extra_prts.length) {
      this.setState({locked: true})
      const actions = this.state.extra_prts.map(p => (
        {act: 'participant:add', participant: p.email}
      ))
      const r = await this.props.ctx.worker.call('act', {conv: this.state.conv.key, actions})
      this.action_ids = r.data.action_ids
      this.setState({extra_prts: null})
    }
  }

  act = async actions => {
    if (!this.state.locked) {
      this.setState({locked: true})
      const r = await this.props.ctx.worker.call('act', {conv: this.state.conv.key, actions})
      this.action_ids = r.data.action_ids
      return r.data.action_ids
    }
  }

  lock_subject = async () => {
    const follows = await this.props.ctx.worker.call('last-subject-action', {conv: this.state.conv.key})
    const action_ids = await this.act([{act: 'subject:lock', follows}])
    return action_ids[0]
  }
  release_subject = async follows => this.act([{act: 'subject:release', follows}])
  set_subject = (subject, follows) => this.act([{act: 'subject:modify', body: subject, follows}])

  render () {
    if (!this.state.conv) {
      return <Loading/>
    }
    const Buttons = this.state.conv.published ? PublishedButtons : DraftButtons
    return (
      <div>
        <div className="h5">
          {!this.state.conv.published && <span className="badge badge-dark mr-2">Draft</span>}
          <span className="badge badge-success mr-2">TODO Labels</span>
        </div>
        <Row>
          <Col md="8">
            {this.state.conv.messages.map(msg => (
              <Message msg={msg}
                       key={msg.first_action}
                       state={this.state}
                       setState={s => this.setState(s)}
                       comment_ref={this.comment_ref}
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
                <textarea placeholder="reply to all..." className="msg"
                          disabled={!!(this.state.locked || this.state.comment_parent || this.state.extra_prts)}
                          value={this.state.new_message || ''}
                          onChange={e => this.setState({new_message: e.target.value})}/>

                <div className="text-right">
                  <Buttons state={this.state} add_msg={this.add_msg} publish={this.publish}/>
                </div>
              </div>
            </div>
          </Col>
          <Col md="4">
            <RightPanel
              conv_state={this.state}
              add_participants={this.add_participants}
              set_participants={extra_prts => this.setState({extra_prts})}
            />
          </Col>
        </Row>
        <EditSubject
          subject={this.state.conv.subject}
          set_subject={this.set_subject}
          lock_subject={this.lock_subject}
          release_subject={this.release_subject}
        />
      </div>
    )
  }
}

export default withRouter(WithContext(ConvDetailsView))
