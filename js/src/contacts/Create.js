import React from 'react'
import {withRouter} from 'react-router-dom'
import {Col, Row} from 'reactstrap'
import {WithContext, Form} from 'reactstrap-toolbox'
import {EditorInput} from './../Editor'
import ImageInput from '../utils/ImageInput'
import {form_fields} from './utils'

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


const Create = ({ctx, history}) => {
  const [form_data, set_form_data] = React.useState({})
  React.useEffect(() => {
    ctx.setMenuItem('contacts')
    ctx.setTitle('Create Contact')
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const submit_data = data => {
    data.details = (data.details && data.details.has_changed) ? data.details.markdown : null
    data.image = data.image ? data.image.file_id : null
    return data
  }

  return (
    <div className="box">
      <Form
        fields={form_fields(form_data)}
        form_data={form_data}
        submit_data={submit_data}
        function={window.logic.contacts.create}
        submitted={r => history.push(`/contacts/${r.data.id}/`)}
        RenderFields={RenderFields}
        type_lookup={{rich_text: EditorInput, image: ImageInput}}
        onChange={set_form_data}
        save_label="Create Contact"
      />
    </div>
  )
}

export default WithContext(withRouter(Create))
