import React from 'react'
import {AsyncTypeahead, Token} from 'react-bootstrap-typeahead'
import {FormGroup, FormFeedback} from 'reactstrap'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {WithContext, InputLabel, InputHelpText, message_toast} from 'reactstrap-toolbox'

const render_option = o => o.name ? `${o.name} <${o.email}>` : o.email
const token = (option, props, index) => (
  <Token key={index} onRemove={props.onRemove}>
    {render_option(option)}
  </Token>
)

const static_props = {
  multiple: true,
  className: 'participants-input',
  minLength: 3,
  filterBy: ['name', 'email'],  // might have to modify this to take care of cases like extra and missing spaces
  labelKey: render_option,
  renderToken: token,
  useCache: false,
  allowNew: false,
  delay: 100,
  selectHintOnEnter: true,
  emptyLabel: 'no match found & invalid email address',
}
const max_participants = 64

class Participants extends React.Component {
  state = {options: [], ongoing_searches: 0}

  selected = () => this.state.options.filter(o => this.props.value.includes(o.email))

  search = async query => {
    this.setState(s => ({ongoing_searches: s.ongoing_searches + 1}))

    const options1 = await window.logic.contacts.fast_email_lookup(query)
    // null when the address is invalid
    if (options1) {
      this.setState({options: options1})
      // this.setState({options: this.selected().concat(options1)})
    }

    const options2 = await window.logic.contacts.slow_email_lookup(query)
    // null when the request was cancelled, or offline
    if (options2 && options2.length) {
      // could combine first and second set of options, but in general second set will override first
      // eg. options2.concat(options1 || [])
      this.setState({options: options2})
    }
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
    }
  }

  render () {
    const count = this.props.value.length
    return (
      <div>
        <AsyncTypeahead
          {...static_props}
          {...this.state}
          isLoading={this.state.ongoing_searches > 0}
          onSearch={this.search}
          selected={this.props.value}
          disabled={this.props.disabled}
          name={this.props.name}
          id={this.props.name}
          required={this.props.required}
          inputProps={{onPaste: this.onPaste}}
          onChange={this.onChange}
        />
        {count ? (
          <small className="text-muted">{count} {count === 1 ? 'Person' : 'People'}</small>
        ) : null}
      </div>
    )
  }
}

const ParticipantsWithContext = WithContext(Participants)

export default ({className, field, disabled, error, value, onChange, existing_participants}) => (
  <FormGroup className={className || field.className}>
    <InputLabel field={field}/>
    <ParticipantsWithContext
      value={value || []}
      disabled={disabled}
      name={field.name}
      id={field.name}
      required={field.required}
      existing_participants={existing_participants || 0}
      onChange={onChange}
    />
    {error && <FormFeedback>{error}</FormFeedback>}
    <InputHelpText field={field}/>
  </FormGroup>
)
