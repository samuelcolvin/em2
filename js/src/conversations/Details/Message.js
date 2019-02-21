import React from 'react'
import {Button, Tooltip} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {format_ts} from '../../lib'
import MessageBody from './MessageBody'

const CommentButton = ({msg, state, setState, comment_ref, children}) => {
  const btn_id = `msg-${msg.last_action}`
  const click = () => {
    setState({comment_parent: msg.first_action, [btn_id]: false})
    setTimeout(() => comment_ref.current.focus(), 0)
  }
  return (
    <div className="text-right">
      <Button size="sm" color="comment" id={btn_id}
              disabled={state.locked || !!state.comment_parent}
              onClick={click}>
        <FontAwesomeIcon icon="reply" className="mr-1"/>
      </Button>
      <Tooltip placement="right" isOpen={state[btn_id]}
               trigger="hover"
               target={btn_id}
               delay={0}
               toggle={() => setState({[btn_id]: !state[btn_id]})}>
        {children}
      </Tooltip>
    </div>
  )
}

const AddComment = ({state, setState, comment_ref, add_comment}) => (
  <div className="d-flex py-1 ml-3">
    <div className="flex-grow-1">
      <textarea placeholder="reply to all..."
                className="msg comment"
                disabled={state.locked}
                value={state.comment || ''}
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
    <div className="ml-3">
      <div className="border-top pt-1 mt-2">
        <b className="mr-1">{msg.creator}</b>
        <span className="text-muted small">{format_ts(msg.created)}</span>
      </div>
      <div>
      <MessageBody msg={msg}/>
      </div>
      <div className="d-flex">
        <div className="flex-grow-1">
          {msg.comments.map(c => <Comment {...props} msg={c} key={c.first_action} depth={depth + 1}/>)}
        </div>
        {depth < 2 && (
          // use visibility to prevent the message body box changing width
          <div className="pl-2 align-self-end" style={{visibility: commenting ? 'hidden' : 'visible'}}>
            <CommentButton {...props} msg={msg}>Reply to Comment</CommentButton>
          </div>
        )}
      </div>
      {commenting && <AddComment {...props}/>}
    </div>
  )
}

export default ({msg, ...props}) => (
  <div className="box no-pad msg-details">
    <div className="border-bottom py-2" id="TestingElement">
      <b className="mr-1">{msg.creator}</b>
      <span className="text-muted small">{format_ts(msg.created)}</span>
    </div>
    <div className="mt-1">
      <MessageBody msg={msg}/>
    </div>
    {Boolean(msg.comments.length) && (
      <div className="pb-2">
        {msg.comments.map(c => <Comment {...props} msg={c} key={c.first_action}/>)}
      </div>
    )}

    {props.state.comment_parent !== msg.last_action ?
      <div className="pb-2">
        <CommentButton {...props} msg={msg}>Reply to Message</CommentButton>
      </div>
      :
      <AddComment {...props}/>
    }
  </div>
)