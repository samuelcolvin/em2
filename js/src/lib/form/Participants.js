import React from 'react'
import {AsyncTypeahead, Token} from 'react-bootstrap-typeahead'
import WithContext from '../context'

const render_option = o => `${o.name} <${o.email}>`
const token = (option, props, index) => (
  <Token key={index} onRemove={props.onRemove} className>
    {render_option(option)}
  </Token>
)

const static_props = {
  multiple: true,
  className: 'participants-input',
  minLength: 3,
  filterBy: ['name', 'email'],
  labelKey: render_option,
  renderToken: token,
  useCache: false,
  allowNew: false
}

class Participants extends React.Component {
  state = {options: [], isLoading: false, selected: []}

  set_publish (publish) {
    const form_data = Object.assign({}, this.state.form_data, {publish})
    this.setState({form_data})
  }

  async search (query) {
    this.setState({isLoading: true})
    let options
    try {
      options = await this.props.ctx.worker.call('contacts-lookup-email', {query})
    } catch (e) {
      if (e.message === 'canceled') {
        // happens when bootstrap-typeahead cancels the request, fine
        return
      } else {
        throw e
      }
    }
    this.setState({isLoading: false, options: options})
  }

  render () {
    return (
      <AsyncTypeahead {...static_props} {...this.state}
                      onSearch={this.search.bind(this)}
                      selected={this.state.options.filter(o => this.props.value.includes(o.email))}
                      disabled={this.props.disabled}
                      name={this.props.name}
                      id={this.props.name}
                      required={this.props.required}
                      onChange={s => this.props.onChange(s.map(s => s.email))}/>
    )
  }
}

export default WithContext(Participants)
