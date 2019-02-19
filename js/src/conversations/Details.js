import React from 'react'
import {Button, Col, Row} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Loading} from '../lib/Errors'
import WithContext from '../lib/context'
import {format_ts} from '../lib'

const CommentButton = ({msg, state, setState, comment_ref, children}) => (
  <Button size="sm" color="comment"
          disabled={state.locked || !!state.comment_parent}
          onClick={() => {
            setState({comment_parent: msg.first_action})
            setTimeout(() => comment_ref.current.focus(), 0)
          }}>
    <FontAwesomeIcon icon="reply" className="mr-1"/>
    {children}
  </Button>
)

const AddComment = ({state, setState, comment_ref, add_comment}) => (
  <div className="d-flex py-1 ml-3">
    <div className="flex-grow-1">
      <textarea placeholder="reply to all..."
                className="msg comment"
                disabled={state.locked}
                value={state.comment}
                ref={comment_ref}
                onChange={e => setState({comment: e.target.value})}/>
    </div>
    <div className="text-right pl-2">
      <div>
        <Button size="sm" color="primary" disabled={state.locked || !state.comment} onClick={add_comment}>
          <FontAwesomeIcon icon="reply" className="mr-1"/>
          Comment
        </Button>
      </div>
      <Button size="sm" color="link" className="text-muted"
            disabled={state.locked}
            onClick={() => setState({comment_parent: null, comment: null})}>
        Cancel
      </Button>
    </div>
  </div>
)

const Comment = ({msg, depth = 1, ...props}) => {
  const commenting = props.state.comment_parent === msg.last_action
  return (
    <div className="ml-3 mt-2">
      <div className="border-top">
        <b className="mr-1">{msg.creator}</b>
        <span className="text-muted small">{format_ts(msg.created)}</span>
      </div>
      <div>
        <ReactMarkdown source={msg.body}/>
      </div>
      <div className="d-flex">
        <div className="flex-grow-1">
          {msg.comments.map(c => <Comment {...props} msg={c} key={c.first_action} depth={depth + 1}/>)}
        </div>
        {depth < 2 && (
          // use visibility to prevent the message body box changing width
          <div className="pl-2 align-self-end" style={{visibility: commenting ? 'hidden' : 'visible'}}>
            <CommentButton {...props} msg={msg}/>
          </div>
        )}
      </div>
      {commenting && <AddComment {...props}/>}
    </div>
  )
}

const Message = ({msg, ...props}) => (
  <div className="box no-pad msg-details">
    <div className="border-bottom py-1">
      <b className="mr-1">{msg.creator}</b>
      <span className="text-muted small">{format_ts(msg.created)}</span>
    </div>
    <div className="mt-1">
      <ReactMarkdown source={msg.body}/>
    </div>
    {Boolean(msg.comments.length) && (
      <div className="pb-1">
        {msg.comments.map(c => <Comment {...props} msg={c} key={c.first_action}/>)}
      </div>
    )}

    {props.state.comment_parent !== msg.last_action ?
      <div className="text-right pb-2">
        <CommentButton {...props} msg={msg}>Comment</CommentButton>
      </div>
      :
      <AddComment {...props}/>
    }
  </div>
)

class ConvDetailsView extends React.Component {
  constructor(props) {
    super(props)
    this.state = {}
    this.comment_ref = React.createRef()
  }

  async componentDidMount () {
    this.mounted = true
    this.update()
    this.remove_listener = this.props.ctx.worker.add_listener('change', this.update)
  }

  componentDidUpdate (prevProps, prevState, snapshot) {
    this.check_locked()
    const prev_msg_count = prevState.messages ? prevState.conv.messages.length : null
    if (prev_msg_count && prev_msg_count < this.state.conv.messages.length) {
      window.scrollTo(0,document.body.scrollHeight)
    }
  }

  componentWillUnmount () {
    this.mounted = false
    this.remove_listener()
  }

  setState (state, callback) {
    this.mounted && super.setState(state, callback)
  }

  update = async () => {
    const conv = await this.props.ctx.worker.call('get-conversation', this.props.match.params)
    this.props.ctx.setTitle(conv.subject)
    // console.log(conv.messages)
    this.setState({conv})
  }

  add_msg = async () => {
    if (this.state.new_message) {
      this.setState({locked: true})
      const act = {act: 'message:add', body: this.state.new_message}
      const r = await this.props.ctx.worker.call('act', {conv: this.props.match.params.key, act})
      this.new_action = r.data.action_id
      this.setState({new_message: null})
    }
  }

  add_comment = async () => {
    if (this.state.comment && this.state.comment_parent) {
      this.setState({locked: true})
      const act = {act: 'message:add', body: this.state.comment, parent: this.state.comment_parent}
      const r = await this.props.ctx.worker.call('act', {conv: this.props.match.params.key, act})
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
    return (
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
                        value={this.state.new_message}
                        onChange={e => this.setState({new_message: e.target.value})}/>

              <div className="text-right">
                <Button color="primary"
                        disabled={this.state.locked || !this.state.new_message}
                        onClick={this.add_msg}>
                  <FontAwesomeIcon icon="paper-plane" className="mr-1"/>
                  Send
                </Button>
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
    )
  }
}

export default withRouter(WithContext(ConvDetailsView))
