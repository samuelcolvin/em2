import React from 'react'
import {
  Button,
  ButtonGroup,
  Tooltip,
  ListGroup,
  ListGroupItem,
  UncontrolledButtonDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {format_ts} from '../../utils/dt'
import {make_url} from '../../logic/network'
import MessageBody from './MessageBody'
import file_icon from './file_icons'

const CommentButton = ({msg, state, setState, comment_ref, children}) => {
  const btn_id = `msg-${msg.last_action}`
  const click = () => {
    setState({comment_parent: msg.first_action, [btn_id]: false})
    setTimeout(() => comment_ref.current.focus(), 0)
  }
  return (
    <div className="text-right">
      <Button size="sm" color="comment" id={btn_id}
              disabled={!!(state.locked || state.comment_parent || state.new_message || state.extra_prts)}
              onClick={click}>
        <FontAwesomeIcon icon={fas.faReply} className="mr-1"/>
      </Button>
      <Tooltip placement="right" isOpen={state[btn_id]}
               trigger="hover"
               target={btn_id}
               delay={0}
               toggle={() => setState(s => ({[btn_id]: !s[btn_id]}))}>
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
          <FontAwesomeIcon icon={fas.faReply} className="mr-1"/>
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
      <MessageBody msg={msg} conv={props.state.conv.key} session_id={props.session_id}/>
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


const Attachments = ({files, session_id, conv}) => {
  const attachments = (files || []).filter(f => f.content_disp === 'attachment')
  if (!attachments.length) {
    return null
  }
  const file_url = f => make_url('ui', `/${session_id}/conv/${conv}/get-image/${f.content_id}`)
  return (
    <div>
      <span className="text-muted">Attachments</span>
      <ListGroup>
        {attachments.map(f => (
          <ListGroupItem key={f.hash} tag="a" href={file_url(f)} action download>
            <FontAwesomeIcon icon={file_icon(f.content_type)} className="mr-2"/>
            <span data-content-type={f.content_type}>{f.name}</span>
          </ListGroupItem>
        ))}
      </ListGroup>
    </div>
  )
}

const MessageWarning = ({msg, conv}) => {
  if (!msg.warnings || msg.hide_warnings) {
    return null
  }
  return (
    <div className="my-2 mx-3 bg-warning rounded py-2">
      <b>Warning:</b>
      <ul className="mb-1">
        {msg.warnings.map((m, i) => (
          <li key={i}><b>{m.title}:</b> {m.message}</li>
        ))}
      </ul>
      <div className="text-right">
        <ButtonGroup>
          <Button size="sm" color="info" href="https://www.example.com/info" target="_blank" rel="noopener noreferrer">
            More Information
          </Button>
          <Button size="sm" onClick={() => toggle_warnings(conv, msg, true)}>
            Close
          </Button>
        </ButtonGroup>
      </div>
    </div>
  )
}

const toggle_warnings = (conv, msg, show) => (
   window.logic.conversations.toggle_warnings(conv, msg.first_action, show)
)

export default ({msg, ...props}) => (
  <div className="box no-pad msg-details">
    <div className="border-bottom py-2 d-flex justify-content-between">
      <div>
        <b className="mr-1">{msg.creator}</b>
        <span className="text-muted small">{format_ts(msg.created)}</span>
      </div>
      <div>
        {msg.warnings && msg.hide_warnings ? (
          <Button size="sm" color="warning" onClick={() => toggle_warnings(props.state.conv.key, msg, false)}>
            Warnings
            <FontAwesomeIcon icon={fas.faRadiation} className="ml-1"/>
          </Button>
        ) : null}
        <UncontrolledButtonDropdown>
          <DropdownToggle color="link" className="p-0 ml-2 text-muted text-decoration-none">
            Options
            <FontAwesomeIcon icon={fas.faCaretDown} className="ml-1"/>
          </DropdownToggle>
          <DropdownMenu right>
            <DropdownItem>Edit Message</DropdownItem>
            <DropdownItem>View Original</DropdownItem>
            <DropdownItem>View History</DropdownItem>
          </DropdownMenu>
        </UncontrolledButtonDropdown>
      </div>
    </div>
    <MessageWarning msg={msg} conv={props.state.conv.key}/>
    <div className="mt-1">
      <MessageBody msg={msg} conv={props.state.conv.key} session_id={props.session_id}/>
      <Attachments files={msg.files} conv={props.state.conv.key} session_id={props.session_id}/>
    </div>
    {msg.comments.length ? (
      <div className="pb-2">
        {msg.comments.map(c => <Comment {...props} msg={c} key={c.first_action}/>)}
      </div>
    ) : null}

    {props.state.comment_parent !== msg.last_action ?
      <div className="pb-2">
        <CommentButton {...props} msg={msg}>Reply to Message</CommentButton>
      </div>
      :
      <AddComment {...props}/>
    }
  </div>
)
