import React from 'react'
import {Button, UncontrolledDropdown, DropdownToggle, DropdownMenu, DropdownItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {on_mobile, WithContext} from 'reactstrap-toolbox'
import {has_content} from '../Editor'
import ParticipantsInput from '../ParticipantsInput'

const scroll_threshold = 108
// needs to match $grid-breakpoints: xl
const width_threshold = 1200
const fixed_top = '103px'

const ScrollSpy = ({children}) => {
  const scroll_ref = React.createRef()
  let fixed = false

  const set_fixed = () => {
    const fix = window.scrollY > scroll_threshold && document.body.offsetWidth > width_threshold
    if (!fixed && fix) {
      fixed = true
      if (scroll_ref.current) {
        scroll_ref.current.style.position = 'fixed'
        scroll_ref.current.style.top = fixed_top
        scroll_ref.current.style.width = document.getElementById('main').offsetWidth / 4 - 30 + 'px'
      }
    } else if (fixed && !fix) {
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


const RightPanel = ({state, edit_locked, set_participants, add_participants, remove_participants, ctx}) => {
  const disabled = !!(edit_locked || state.comment_parent || has_content(state.new_message))
  return (
    <ScrollSpy>
      <div className="box no-pad pb-3">
        <div className="border-bottom py-2 d-flex justify-content-between">
          <div>
            <b className="mr-1">Participants</b>
          </div>

          <div>
            {on_mobile &&
              <Button color="link"
                      disabled={disabled}
                      size="sm"
                      className="p-0 ml-2 text-decoration-none"
                      onClick={() => set_participants([])}>
                Add
              </Button>
            }
          </div>
        </div>
        {Object.values(state.conv.participants).map(p => (
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
        {state.extra_prts ? (
          <div className="mt-2">
            <ParticipantsInput
              field={{name: 'participants'}}
              value={state.extra_prts}
              disabled={edit_locked}
              existing_participants={Object.keys(state.conv.participants).length}
              onChange={extra_prts => set_participants(extra_prts)}
            />

            <div className="d-flex flex-row-reverse mt-2">
              <Button color="primary" disabled={edit_locked} size="sm" onClick={add_participants}>
                Add
              </Button>
              <Button size="sm" color="link" className="text-muted"
                      disabled={edit_locked}
                      onClick={() => set_participants(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : !on_mobile && (
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
