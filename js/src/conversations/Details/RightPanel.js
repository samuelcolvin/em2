import React from 'react'
import {Link} from 'react-router-dom'
import {
  Button,
  ButtonGroup,
  UncontrolledButtonDropdown,
  DropdownToggle,
  DropdownMenu,
  DropdownItem,
} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {WithContext} from 'reactstrap-toolbox'
import ParticipantsInput from '../ParticipantsInput'


const ScrollSpy = ({scroll_threshold, fixed_top, children}) => {
  const scroll_ref = React.createRef()
  let styled = false

  const set_fixed = () => {
    if (!styled && window.scrollY > scroll_threshold) {
      styled = true
      if (scroll_ref.current) {
        scroll_ref.current.style.position = 'fixed'
        scroll_ref.current.style.top = fixed_top + 'px'
        scroll_ref.current.style.width = document.getElementById('main').offsetWidth / 3 - 30 + 'px'
      }
    } else if (styled && window.scrollY <= scroll_threshold) {
      styled = false
      if (scroll_ref.current) {
        scroll_ref.current.style.position = 'static'
      }
    }
  }

  React.useEffect(() => {
    window.addEventListener('scroll', set_fixed)
    return () => window.removeEventListener('scroll', set_fixed)
  })

  return <div ref={scroll_ref}>{children}</div>
}


const RightPanel = ({conv_state, set_participants, add_participants}) => (
  <ScrollSpy scroll_threshold={45} fixed_top={103}>
    <ButtonGroup vertical className="btn-group-box">
      <Button color="box" tag={Link} to="./edit-subject/">Edit Subject</Button>

      <UncontrolledButtonDropdown direction="right">
        <DropdownToggle color="box" className="border-top">
          More <FontAwesomeIcon icon="caret-right"/>
        </DropdownToggle>
        <DropdownMenu>
          <DropdownItem>Thing one</DropdownItem>
          <DropdownItem>Thing two</DropdownItem>
          <DropdownItem>Thing three</DropdownItem>
        </DropdownMenu>
      </UncontrolledButtonDropdown>
    </ButtonGroup>
    <div className="box">
      {Object.keys(conv_state.conv.participants).map((p, i) => (
        <div key={i}>{p}</div>
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
                  disabled={!!(conv_state.locked || conv_state.comment_parent || conv_state.new_message)}
                  size="sm"
                  onClick={() => set_participants([])}>
            Add Participants
          </Button>
        </div>
      )}
    </div>
  </ScrollSpy>
)

export default WithContext(RightPanel)
