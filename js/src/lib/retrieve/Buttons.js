import React from 'react'
import {Link} from 'react-router-dom'
import {
  Button,
  ButtonGroup,
} from 'reactstrap'
import ButtonConfirm from './Confirm'

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
