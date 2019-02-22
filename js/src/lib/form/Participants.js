import React from 'react'
import {AsyncTypeahead, Token} from 'react-bootstrap-typeahead'
import WithContext from '../context'

const render_option = o => o.name ? `${o.name} <${o.email}>` : o.email
const token = (option, props, index) => (
  <Token key={index} onRemove={props.onRemove} className>
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
}
class Participants extends React.Component {
  state = {options: [], ongoing_searches: 0}

  selected = () => this.state.options.filter(o => this.props.value.includes(o.email))

  search = async query => {
    this.setState({ongoing_searches: this.state.ongoing_searches + 1})

    const options1 = await this.props.ctx.worker.call('fast-email-lookup', {query})
    // null when the address is invalid
    if (options1) {
      this.setState({options: options1})
      // this.setState({options: this.selected().concat(options1)})
    }

    const options2 = await this.props.ctx.worker.call('slow-email-lookup', {query})
    // null when the request was cancelled, or offline
    // console.log(options1, options2)
    if (options2 && options2.length) {
      // could combine first and second set of options, but in general second set will override first
      // eg. options2.concat(options1 || [])
      this.setState({options: options2})
    }
    this.setState({ongoing_searches: this.state.ongoing_searches - 1})
  }

  render () {
    const count = this.props.value.length
    return (
      <div>
        <AsyncTypeahead {...static_props} {...this.state} isLoading={this.state.ongoing_searches > 0}
                      onSearch={this.search}
                      selected={this.props.value}
                      disabled={this.props.disabled}
                      name={this.props.name}
                      id={this.props.name}
                      required={this.props.required}
                      onChange={s => this.props.onChange(s)}/>
        {count ? (
          <small className="text-muted">{count} {count === 1 ? 'Person' : 'People'}</small>
        ) : null}
      </div>
    )
  }
}

export default WithContext(Participants)
