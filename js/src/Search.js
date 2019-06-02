import React from 'react'
import {withRouter} from 'react-router-dom'
import {Highlighter} from 'react-bootstrap-typeahead'
import {Dropdown, DropdownToggle, DropdownMenu, DropdownItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'


class Search extends React.Component {
  constructor (props) {
    super(props)
    this.state = this.clean_state()
    this.input_ref = React.createRef()
  }

  componentDidMount() {
    this.get_searches()
  }

  clean_state = () => ({convs: [], recent_searches: [], ongoing_searches: 0, query: '', open: false, selection: 0})

  clean = () => {
    this.setState(this.clean_state())
    this.input_ref.current && this.input_ref.current.blur()
  }

  get_searches = async query => {
    this.setState(s => ({ongoing_searches: s.ongoing_searches + 1}))
    this.setState({recent_searches: await window.logic.search.recent_searches(query)})
    this.setState(s => ({ongoing_searches: s.ongoing_searches - 1}))
  }

  search = async query => {
    this.setState(s => ({ongoing_searches: s.ongoing_searches + 1}))

    const convs = await window.logic.search.search(query)
    // null when the request was cancelled, or offline
    if (convs) {
      this.setState({convs})
    }
    // TODO deal with the case that we've called clean by now
    this.setState(s => ({ongoing_searches: s.ongoing_searches - 1}))
  }

  onChange = e => {
    const query = e.target.value
    this.setState({query, selection: 0})
    this.search(query)
    this.get_searches(query)
  }

  selection_max = () => this.state.convs.length + 1

  onKeyDown = e => {
    if (e.key === 'Enter') {
      e.preventDefault()
      this.onEnter()
    } else if (e.key === 'ArrowDown') {
      this.setState(s => ({selection: (s.selection + 1) % this.selection_max()}))
    } else if (e.key === 'ArrowUp') {
      this.setState(s => ({selection: s.selection === 0 ? 4 : (s.selection - 1) % this.selection_max()}))
    } else if (e.key === 'Escape') {
      this.setState({open: false})
    }
  }

  onEnter = () => {
    let selection = this.state.selection
    if (selection === 0) {
      throw Error('not implemented')
    }
    const conv = this.state.convs[selection + 1]
    if (conv) {
      this.onSelect(conv.key)
    }
  }

  onSelect = (key, query) => {
    window.logic.search.mark_visible(this.state.query)
    this.clean()
    this.props.history.push(`/${key}/`)
  }

  render () {
    const open = Boolean(this.state.open && (this.state.convs.length || this.state.recent_searches.length))
    return (
      <Dropdown id="search" isOpen={open} toggle={() => this.setState(s => ({open: !s.open}))}>
        <DropdownToggle tag="div">
          <input
            className="form-control"
            type="text"
            placeholder="Search..."
            ref={this.input_ref}
            value={this.state.query}
            onChange={this.onChange}
            onKeyDown={this.onKeyDown}
          />
        </DropdownToggle>
        <DropdownMenu>
          <RecentSearches {...this.state} onClick={this.onSelect}/>
          <Conversations {...this.state} onClick={this.onSelect}/>
        </DropdownMenu>
      </Dropdown>
    )
  }
}

const RecentSearches = ({recent_searches, convs, selection, onClick}) => {
  if (!recent_searches.length) {
    return null
  }
  return [
    <DropdownItem key="h" header>Recent Searches</DropdownItem>,
    ...recent_searches.map((q, i) => (
      <DropdownItem key={i} active={selection === i + 1} onClick={() => onClick(null, q)}>
        <FontAwesomeIcon icon={fas.faSearch} className="mr-2"/>
        {q}
      </DropdownItem>
    )),
    convs.length ? <DropdownItem key="d" divider /> : null,
  ]
}

const Conversations = ({onClick, convs, selection, query}) => {
  if (!convs.length) {
    return null
  }

  return [
    <DropdownItem key="h" header>Conversations</DropdownItem>,
    ...convs.map((c, i) => (
      <DropdownItem key={c.key} active={selection === i + 1} onClick={() => onClick(c.key)}>
        <div className="d-flex justify-content-between">
          <div>
            <FontAwesomeIcon icon={fas.faEnvelope} className="mr-2"/>
            <Highlighter search={query}>
              {c.details.sub}
            </Highlighter>
          </div>
          <div className="text-muted small">
            {c.key.substr(0, 7)}
          </div>
        </div>
      </DropdownItem>
    )),
  ]
}
export default withRouter(Search)
