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

  search = async query => {
    this.setState(s => ({ongoing_searches: s.ongoing_searches + 1}))
    const skip = new Set(this.props.value.map(v => v.email))

    await window.logic.contacts.email_lookup(query,o => {
      if (!skip.has(o.email)) {
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
      this.setState(s => {
        const options = Object.assign({}, s.options)
        for (let a of addresses) {
          delete options[a.email]
        }
        return {options}
      })
    }
  }

  render () {
    const count = this.props.value.length
    return (
      <div>
        <AsyncTypeahead
          {...static_props}
          options={Object.values(this.state.options).reverse()}
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
