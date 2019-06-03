import React from 'react'
import {withRouter} from 'react-router-dom'
import {Highlighter} from 'react-bootstrap-typeahead'
import {Dropdown, DropdownToggle, DropdownMenu, DropdownItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {sleep} from 'reactstrap-toolbox'


class Search extends React.Component {
  constructor (props) {
    super(props)
    this.state = this.clean_state()
    this.input_ref = React.createRef()
  }

  componentDidMount () {
    this.get_searches()
    if (this.props.location.pathname === '/search/') {
      const query = decodeURI(this.props.location.search.substr(1))
      this.setState({query})
      this.get_searches(query)
    }
  }

  componentDidUpdate (prevProps) {
    const p = this.props.location.pathname
    if (p !== prevProps.location.pathname && p !== '/search/') {
      this.clean()
    }
  }

  clean_state = () => ({convs: [], recent_searches: [], ongoing_searches: 0, query: '', open: false, selection: 0})

  clean = () => {
    this.setState(this.clean_state())
    this.input_ref.current && this.input_ref.current.blur()
    this.get_searches()
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
    this.setState({query, selection: 0, open: true})
    this.search(query)
    this.get_searches(query)
  }

  selection_max = () => this.state.convs.length + this.state.recent_searches.length + 1

  onKeyDown = e => {
    if (e.key === 'Enter') {
      e.preventDefault()
      this.onEnter()
    } else if (e.key === 'ArrowDown') {
      this.setState(s => ({selection: (s.selection + 1) % this.selection_max()}))
    } else if (e.key === 'ArrowUp') {
      const m = this.selection_max()
      this.setState(s => ({selection: s.selection === 0 ? m : (s.selection - 1) % m}))
    } else if (e.key === 'Escape') {
      this.setState({open: false})
    }
  }

  onEnter = () => {
    let selection = this.state.selection
    if (selection === 0) {
      this.pageSearch(this.state.query)
      return
    }
    if (selection <= this.state.recent_searches.length) {
      const rc = this.state.recent_searches[selection - 1]
      this.pageSearch(rc)
    } else {
      const conv = this.state.convs[selection - this.state.recent_searches.length - 1]
      if (conv) {
        this.onSelect(conv.key)
      }
    }
  }

  pageSearch = async query => {
    if (query.length < window.logic.search.min_length) {
      return
    }
    if (this.state.query === '' || !query.startsWith(this.state.query)) {
      this.setState({query})
    }
    window.logic.search.mark_visible(query)
    this.props.history.push(`/search/?${encodeURI(query)}`)
    await sleep(100)
    this.setState({open: false})
  }

  onSelect = key => {
    window.logic.search.mark_visible(this.state.query)
    this.clean()
    this.props.history.push(`/${key.substr(0, 10)}/`)
  }

  render () {
    const open = Boolean(this.state.open && (this.state.convs.length || this.state.recent_searches.length))
    return (
      <Dropdown id="search" isOpen={open} toggle={() => this.setState(s => ({open: !s.open}))}>
        <DropdownToggle tag="div">
          <input
            className="form-control pr-4"
            type="text"
            placeholder="Search..."
            ref={this.input_ref}
            value={this.state.query}
            onChange={this.onChange}
            onKeyDown={this.onKeyDown}
          />
          <div className={this.state.ongoing_searches ? 'rbt-aux' : 'd-none'}>
            <div className="rbt-loader"/>
          </div>
        </DropdownToggle>
        <DropdownMenu>
          <RecentSearches {...this.state} pageSearch={this.pageSearch}/>
          <Conversations {...this.state} onSelect={this.onSelect}/>
        </DropdownMenu>
      </Dropdown>
    )
  }
}

const RecentSearches = ({recent_searches, convs, selection, query, pageSearch}) => {
  if (!recent_searches.length) {
    return null
  }
  return [
    <DropdownItem key="h" header>Recent Searches</DropdownItem>,
    ...recent_searches.map((q, i) => (
      <DropdownItem key={i} active={selection === i + 1} onClick={() => pageSearch(q)}>
        <FontAwesomeIcon icon={fas.faSearch} className="mr-2 text-muted small"/>
        <Highlighter search={query}>
          {q}
        </Highlighter>
      </DropdownItem>
    )),
    convs.length ? <DropdownItem key="d" divider /> : null,
  ]
}

const Conversations = ({recent_searches, convs, selection, query, onSelect}) => {
  if (!convs.length) {
    return null
  }
  selection = selection - recent_searches.length
  return [
    <DropdownItem key="h" header>Conversations</DropdownItem>,
    ...convs.map((c, i) => (
      <DropdownItem key={c.key} active={selection === i + 1} onClick={() => onSelect(c.key)}>
        <div className="d-flex justify-content-between">
          <div>
            <FontAwesomeIcon icon={fas.faEnvelope} className="mr-2 text-muted small"/>
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
