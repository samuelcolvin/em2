import React from 'react'
import {withRouter} from 'react-router-dom'
import {AsyncTypeahead, Token, Highlighter} from 'react-bootstrap-typeahead'
import {FormGroup, FormFeedback} from 'reactstrap'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext, InputLabel, InputHelpText, message_toast} from 'reactstrap-toolbox'
import jw_distance from 'jaro-winkler'

const renderToken = (option, props, index) => (
  <Token key={index} onRemove={props.onRemove}>
    {option.main_name ? (
      <div>
        {option.main_name} {option.last_name || ''}
        <div>
          <small className="text-muted">{option.email}</small>
        </div>
      </div>
    ) : (
      <div>{option.email}</div>
    )}
  </Token>
)

const renderMenuItemChildren = (option, props) => {
  if (option.main_name) {
    return [
      <div key="1">
        <Highlighter search={props.text}>
          {`${option.main_name} ${option.last_name || ''}`}
        </Highlighter>
      </div>,
      <small key="2" className="text-muted">
        <Highlighter search={props.text}>
          {option.email}
        </Highlighter>
      </small>,
    ]
  } else {
    return [
      <div key="1">
        <Highlighter search={props.text}>
          {option.email}
        </Highlighter>
      </div>,
      <small key="2" className="text-muted">
        &nbsp;
      </small>,
    ]
  }
}

const static_props = {
  renderMenuItemChildren,
  renderToken,
  filterBy: () => true,
  multiple: true,
  className: 'participants-input',
  minLength: 3,
  labelKey: 'email',
  useCache: false,
  allowNew: false,
  delay: 100,
  selectHintOnEnter: true,
  emptyLabel: 'no match found & invalid email address',
}
const max_participants = 64

class Participants extends React.Component {
  state = {options: [], ongoing_searches: 0, text: ''}

  async componentDidMount() {
    // could maybe do this more efficiently using multiple get args
    const m = this.props.location.search.match(/participant=([^&=]+)/i)
    if (m) {
      await window.logic.contacts.email_lookup(m[1],o => this.props.onChange([o]))
      this.props.history.replace(this.props.location.pathname)
    }
  }

  search = async query => {
    this.setState(s => ({ongoing_searches: s.ongoing_searches + 1}))
    const skip = new Set([...this.props.value.map(v => v.email), ...(this.props.ignore || [])])

    await window.logic.contacts.email_lookup(query,o => {
      if (!skip.has(o.email)) {
        const ref = [o.email, o.main_name, o.last_name, o.strap_line]
        Object.assign(o, {ref: ref.filter(v => v).join(' ').toLowerCase()})
        this.setState(s => ({options: Object.assign({}, s.options, {[o.email]: o})}))
      }
    })

    this.setState(s => ({ongoing_searches: s.ongoing_searches - 1}))
  }

  onPaste = async e => {
    const raw = e.clipboardData.getData('Text')
    if (raw) {
      e.preventDefault()
      const [addresses, bad_count] = await window.logic.contacts.parse_multiple_addresses(raw)
      if (addresses) {
        this.onChange(this.props.value.concat(addresses))
      }
      if (bad_count) {
        message_toast({icon: fas.faTimes, message: `Skipped ${bad_count} invalid addresses while pasting`})
      }
    }
  }

  onChange = addresses => {
    const existing_participants = this.props.existing_participants || 0
    if (existing_participants + addresses.length > max_participants) {
      message_toast({icon: fas.faTimes, message: `Maximum ${max_participants} participants permitted`})
    } else {
      this.props.onChange(addresses)
      this.setState({options: {}})
    }
  }

  distance = o => o.ref.includes(this.state.text) + jw_distance(this.state.text, o.ref)

  render () {
    const count = this.props.value.length
    const options = Object.values(this.state.options)
      .map(o => Object.assign(o, {s: this.distance(o)}))
      .sort((a, b) => b.s - a.s)

    const input_id = this.props.id || 'participants-input'
    const input_name = this.props.name || 'participants-input'
    return (
      <div>
        <AsyncTypeahead
          {...static_props}
          options={options}
          isLoading={this.state.ongoing_searches > 0}
          onSearch={this.search}
          selected={this.props.value}
          disabled={this.props.disabled}
          name={input_name}
          id={input_id}
          required={this.props.required}
          inputProps={{onPaste: this.onPaste, id: input_id, name: input_name}}
          onChange={this.onChange}
          onInputChange={t => this.setState({text: t.toLocaleString()})}
        />
        {count ? (
          <small className="text-muted">{count} {count === 1 ? 'Person' : 'People'}</small>
        ) : null}
      </div>
    )
  }
}

const ParticipantsWithContext = WithContext(withRouter(Participants))

export default ({className, field, error, value, existing_participants, ...props}) => (
  <FormGroup className={className || field.className}>
    <InputLabel field={field}/>
    <ParticipantsWithContext
      value={value || []}
      name={field.name}
      id={field.name}
      required={field.required}
      existing_participants={existing_participants || 0}
      {...props}
    />
    {error && <FormFeedback>{error}</FormFeedback>}
    <InputHelpText field={field}/>
  </FormGroup>
)
