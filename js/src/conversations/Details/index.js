import React from 'react'
import {Button, ButtonGroup, Col, Row} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Loading} from '../../lib/Errors'
import WithContext from '../../lib/context'
import Message from './Message'

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
  }

  componentDidUpdate (prevProps, prevState, snapshot) {
    if (this.props.location !== prevProps.location) {
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
  }

  setState (state, callback) {
    this.mounted && super.setState(state, callback)
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
      this.check_locked()
    }
  }

  publish = async () => {
    if (!this.state.conv.published) {
      this.setState({locked: true})
      await this.props.ctx.worker.call('publish', {conv: this.state.conv.key})
    }
  }

  add_msg = async () => {
    if (this.state.new_message) {
      this.setState({locked: true})
      const act = {act: 'message:add', body: this.state.new_message}
      const r = await this.props.ctx.worker.call('act', {conv: this.state.conv.key, act})
      this.new_action = r.data.action_id
      this.setState({new_message: null})
    }
  }

  add_comment = async () => {
    if (this.state.comment && this.state.comment_parent) {
      this.setState({locked: true})
      const act = {act: 'message:add', body: this.state.comment, parent: this.state.comment_parent}
      const r = await this.props.ctx.worker.call('act', {conv: this.state.conv.key, act})
      this.new_action = r.data.action_id
      this.setState({comment: null, comment_parent: null})
    }
  }

  check_locked = () => {
    if (this.new_action && this.state.locked && this.state.conv.action_ids.has(this.new_action)) {
      this.new_action = null
      this.setState({locked: false})
    }
  }

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
                          disabled={this.state.locked}
                          value={this.state.new_message || ''}
                          onChange={e => this.setState({new_message: e.target.value})}/>

                <div className="text-right">
                  <Buttons state={this.state} add_msg={this.add_msg} publish={this.publish}/>
                </div>
              </div>
            </div>
          </Col>
          <Col md="4">
            <div className="box">
              {Object.keys(this.state.conv.participants).map((p, i) => (
                  <div key={i}>{p}</div>
              ))}
            </div>
          </Col>
        </Row>
      </div>
    )
  }
}

export default withRouter(WithContext(ConvDetailsView))
