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
import Participants from '../../lib/form/Participants'
import WithContext from '../../lib/context'

class ScrollSpy extends React.Component {
  state = {style: null}

  set_fixed = () => {
    const scroll_y = window.scrollY
    if (scroll_y > this.props.scroll_threshold && !this.state.style) {
      const width = document.getElementById('main').offsetWidth / 3 - 30 + 'px'
      this.setState({style: {position: 'fixed', top: this.props.fixed_top + 'px', width}})
    } else if (scroll_y <= this.props.scroll_threshold && this.state.style) {
      this.setState({style: null})
    }
  }

  componentDidMount () {
    window.addEventListener('scroll', this.set_fixed)
  }

  componentWillUnmount () {
    window.removeEventListener('scroll', this.set_fixed)
  }

  render () {
    return <div style={this.state.style}>{this.props.children}</div>
  }
}


class RightPanel extends React.Component {
  render () {
    const conv_state = this.props.conv_state
    return (
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
              <Participants name="participants"
                            ctx={this.props.ctx}
                            value={conv_state.extra_prts || []}
                            disabled={conv_state.locked}
                            existing_participants={Object.keys(conv_state.conv.participants).length}
                            onChange={extra_prts => this.props.set_participants(extra_prts)}/>

              <div className="d-flex flex-row-reverse mt-2">
                <Button color="primary" disabled={conv_state.locked} size="sm"
                        onClick={this.props.add_participants}>
                  Add
                </Button>
                <Button size="sm" color="link" className="text-muted"
                        disabled={conv_state.locked}
                        onClick={() => this.props.set_participants(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-right mt-2">
              <Button color="primary"
                      disabled={!!(conv_state.locked || conv_state.comment_parent || conv_state.new_message)}
                      size="sm"
                      onClick={() => this.props.set_participants([])}>
                Add Participants
              </Button>
            </div>
          )}
        </div>
      </ScrollSpy>
    )
  }
}

export default WithContext(RightPanel)
