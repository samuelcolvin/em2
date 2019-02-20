import React from 'react'
import {Button, Col, Row} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Loading} from '../../lib/Errors'
import WithContext from '../../lib/context'
import Message from './Message'

class ConvDetailsView extends React.Component {
  constructor (props) {
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
    const prev_msg_count = prevState.conv ? prevState.conv.messages.length : null
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
                        value={this.state.new_message || ''}
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
