import React from 'react'
import {withRouter} from 'react-router-dom'
import {Col, Row} from 'reactstrap'
import {WithContext, Form, Loading} from 'reactstrap-toolbox'
import {EditorInput} from './../Editor'
import ImageInput from '../utils/ImageInput'
import {contact_name, form_fields} from './utils'

const RenderFields = ({fields, RenderField}) => (
  <Row>
    <Col lg="4">
      <div className="image-preview-right text-right">
        <RenderField field={fields.image}/>
      </div>
    </Col>
    <Col lg="8">
      <RenderField field={fields.email}/>
      <RenderField field={fields.profile_type}/>
      <RenderField field={fields.main_name}/>
      <RenderField field={fields.last_name} optional/>
      <RenderField field={fields.strap_line}/>
      <RenderField field={fields.details}/>
    </Col>
  </Row>
)


class Edit extends React.Component {
  state = {form_data: {}}

  componentDidMount () {
    this.props.ctx.setTitle('Edit Contact')
    this.update()
  }

  componentDidUpdate (prevProps) {
    if (this.props.location !== prevProps.location) {
      this.update()
    }
  }

  update = async () => {
    this.props.ctx.setMenuItem('contacts')
    const initial = await window.logic.contacts.edit_initial(this.props.match.params.id)
    if (initial) {
      this.setState({initial})
      this.props.ctx.setTitle(`Edit ${contact_name(initial)}`)
    } else {
      this.setState({not_found: true})
    }
  }

  submit_data = data => {
    data.details = (data.details && data.details.has_changed) ? data.details.markdown : null
    data.image = data.image ? data.image.file_id : null
    data.id = this.props.match.params.id
    return data
  }

  render () {
    if (this.state.not_found) {
      return <div>Contact not found.</div>
    }
    if (!this.state.initial) {
      return <Loading/>
    }
    const details_path = `/contacts/${this.props.match.params.id}/`
    return (
      <div className="box">
        <Form
          fields={form_fields(this.state.form_data)}
          initial={this.state.initial}
          form_data={this.state.form_data}
          submit_data={this.submit_data}
          function={window.logic.contacts.edit}
          submitted={() => this.props.history.push(details_path)}
          RenderFields={RenderFields}
          type_lookup={{rich_text: EditorInput, image: ImageInput}}
          onChange={form_data => this.setState({form_data})}
          done={() => this.props.history.push(details_path)}
        />
      </div>
    )
  }
}

export default WithContext(withRouter(Edit))
