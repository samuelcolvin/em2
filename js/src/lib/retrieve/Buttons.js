import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {
  Button,
  ButtonGroup,
} from 'reactstrap'
import ButtonConfirm from './Confirm'

export const render = v => {
  if (typeof v === 'boolean') {
    return <FontAwesomeIcon icon={v ? 'check' : 'times'}/>
  } else if ([null, undefined].includes(v)) {
    return <Dash/>
  } else if (typeof v === 'object') {
    if (Object.keys(v).includes('$$typeof')) {
      return v
    } else {
      return JSON.stringify(v)
    }
  } else {
    return v
  }
}

export const Dash = () => <span>&mdash;</span>

export const Detail = ({name, wide, edit_link, children}) => (
  <div className={`item-detail${wide ? ' wide' : ''}`}>
    <div className="key">
      {name}
      {edit_link && <Button tag={Link} to={edit_link} size="sm" className="ml-2">
        <FontAwesomeIcon icon="pencil-alt" className="mr-1"/>
        Edit {name}
      </Button>}
    </div>
    <div className="value">
      {render(children)}
    </div>
  </div>
)

export default ({buttons, ctx}) => (
  buttons ? <div className="text-right mb-2">
    <ButtonGroup className="btn-divider">
      {buttons.filter(b => b).map(b => (
        b.confirm_msg ?
          <ButtonConfirm key={b.name}
                         action={b.action}
                         modal_title={b.name}
                         btn_text={b.name}
                         redirect_to={b.redirect_to}
                         success_msg={b.success_msg}
                         done={b.done}
                         btn_color={b.btn_color}
                         btn_size="sm"
                         className="ml-2">
            {b.confirm_msg}
          </ButtonConfirm>
          :
          <Button key={b.name} tag={Link} to={b.link} disabled={b.disabled || false}>{b.name}</Button>
      ))}
    </ButtonGroup>
  </div> : <div/>
)
