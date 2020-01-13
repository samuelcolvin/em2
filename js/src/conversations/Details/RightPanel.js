import React from 'react'
import {Button, UncontrolledDropdown, DropdownToggle, DropdownMenu, DropdownItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {on_mobile, combine_classes, WithContext} from 'reactstrap-toolbox'
import ParticipantsInput from '../ParticipantsInput'
import {ContactImage} from '../../contacts/utils'

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

const ParticipantSummary = ({participant, className}) => (
  <div className={combine_classes(className, 'd-flex justify-content-start')}>
    <div className="mr-2 mt-1">
      <ContactImage c={participant}/>
    </div>
    <div>
      <div>
        {participant.name}
      </div>
      <small className="text-muted">
        {participant.email}
      </small>
    </div>
  </div>
)


const RightPanel = ({state, locked, set_participants, add_participants, remove_participants, ctx}) => {
  const disabled = locked('extra_prts')
  const add_prts = () => {
    set_participants([])
    setTimeout(() => document.getElementById('participants').focus(), 100)
  }

  const participants = Object.values(state.conv.participants)

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
        {participants.map(p => (
          <div key={p.id} className="d-flex justify-content-between py-2">
            <ParticipantSummary participant={p}/>
            <div>
              {p.email !== ctx.user.email ? (
                <UncontrolledDropdown>
                  <DropdownToggle color="link" size="sm" disabled={disabled} className="py-0 mb-0">
                    edit <FontAwesomeIcon icon={fas.faCaretDown}/>
                  </DropdownToggle>
                  <DropdownMenu right>
                    <DropdownItem onClick={() => remove_participants(p)}>Remove</DropdownItem>
                  </DropdownMenu>
                </UncontrolledDropdown>
              ) : null}
            </div>
          </div>
        ))}
        {state.extra_prts ? (
          <div className="mt-2">
            <ParticipantsInput
              field={{name: 'participants'}}
              value={state.extra_prts}
              disabled={disabled}
              existing_participants={Object.keys(state.conv.participants).length}
              onChange={extra_prts => set_participants(extra_prts)}
              ignore={participants.map(p => p.email)}
            />

            <div className="d-flex flex-row-reverse mt-2">
              <Button color="primary" disabled={disabled} size="sm" onClick={add_participants}>
                Add
              </Button>
              <Button size="sm" color="link" className="text-muted"
                      disabled={disabled}
                      onClick={() => set_participants(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : !on_mobile && (
          <div className="text-right mt-2">
            <Button color="primary" disabled={disabled} size="sm" onClick={add_prts}>
              Add Participants
            </Button>
          </div>
        )}
      </div>
    </ScrollSpy>
  )
}

export default WithContext(RightPanel)
