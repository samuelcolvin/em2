import React from 'react'
import {Button, UncontrolledDropdown, DropdownToggle, DropdownMenu, DropdownItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext} from 'reactstrap-toolbox'
import ParticipantsInput from '../ParticipantsInput'


const ScrollSpy = ({children}) => {
  const scroll_ref = React.createRef()
  let fixed = false

  const scroll_threshold = 108
  const fixed_top = '103px'

  const set_fixed = () => {
    if (!fixed && window.scrollY > scroll_threshold) {
      fixed = true
      if (scroll_ref.current) {
        scroll_ref.current.style.position = 'fixed'
        scroll_ref.current.style.top = fixed_top
        scroll_ref.current.style.width = document.getElementById('main').offsetWidth / 4 - 30 + 'px'
      }
    } else if (fixed && window.scrollY <= scroll_threshold) {
      fixed = false
      if (scroll_ref.current) {
        scroll_ref.current.style.position = null
        scroll_ref.current.style.top = null
        scroll_ref.current.style.width = null
      }
    }
  }

  React.useEffect(() => {
    window.addEventListener('scroll', set_fixed)
    return () => window.removeEventListener('scroll', set_fixed)
  })

  return <div ref={scroll_ref}>{children}</div>
}


const RightPanel = ({conv_state, set_participants, add_participants, remove_participants, ctx}) => {
  const disabled = !!(conv_state.locked || conv_state.comment_parent || conv_state.new_message)
  return (
    <ScrollSpy>
      <div className="box">
        {Object.values(conv_state.conv.participants).map(p => (
          <div key={p.id} className="d-flex">
            <div className="py-1">{p.email}</div>
            {p.email !== ctx.user.email ? (
              <UncontrolledDropdown>
                <DropdownToggle color="link" size="sm" disabled={disabled}>
                  edit <FontAwesomeIcon icon={fas.faCaretDown}/>
                </DropdownToggle>
                <DropdownMenu>
                  <DropdownItem onClick={() => remove_participants(p)}>Remove</DropdownItem>
                </DropdownMenu>
              </UncontrolledDropdown>
            ) : null}
          </div>
        ))}
        {conv_state.extra_prts ? (
          <div className="mt-2">
            <ParticipantsInput
              field={{name: 'participants'}}
              value={conv_state.extra_prts}
              disabled={conv_state.locked}
              existing_participants={Object.keys(conv_state.conv.participants).length}
              onChange={extra_prts => set_participants(extra_prts)}
            />

            <div className="d-flex flex-row-reverse mt-2">
              <Button color="primary" disabled={conv_state.locked} size="sm" onClick={add_participants}>
                Add
              </Button>
              <Button size="sm" color="link" className="text-muted"
                      disabled={conv_state.locked}
                      onClick={() => set_participants(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="text-right mt-2">
            <Button color="primary"
                    disabled={disabled}
                    size="sm"
                    onClick={() => set_participants([])}>
              Add Participants
            </Button>
          </div>
        )}
      </div>
    </ScrollSpy>
  )
}

export default WithContext(RightPanel)
