import React from 'react'
import {withRouter} from 'react-router-dom'
import {Col, Row} from 'reactstrap'
import {WithContext, Form} from 'reactstrap-toolbox'
import {EditorInput} from './../Editor'

const RenderFields = ({fields, RenderField}) => (
  <Row>
    <Col lg="4">
    </Col>
    <Col lg="8">
      <RenderField field={fields.email}/>
      <RenderField field={fields.profile_type} optional/>
      <RenderField field={fields.main_name} optional/>
      <RenderField field={fields.last_name} optional/>
      <RenderField field={fields.strap_line} optional/>
      <RenderField field={fields.body} optional/>
    </Col>
  </Row>
)


const Create = ({ctx, history}) => {
  const [form_data, set_form_data] = React.useState({})
  React.useEffect(() => {
    ctx.setMenuItem('contacts')
    ctx.setTitle('Create Contact')
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  let fields = {
    email: {max_length: 255, type: 'email'},
    profile_type: {type: 'select', choices: ['personal', 'work', 'organisation'], default: 'personal'},
    main_name: {title: 'First Name', max_length: 63},
    last_name: {max_length: 63},
    strap_line: {max_length: 127},
    body: {type: 'rich_text'},
  }
  if (form_data.profile_type === 'organisation') {
    fields = {
      email: {max_length: 255, type: 'email'},
      profile_type: {type: 'select', choices: ['personal', 'work', 'organisation']},
      main_name: {title: 'Name', max_length: 63},
      strap_line: {max_length: 127},
      body: {type: 'rich_text'},
    }
  }

  return (
    <div className="box">
      <Form
        fields={fields}
        form_data={form_data}
        function={window.logic.contacts.create}
        submitted={r => history.push(`/contacts/${r.data.id}/`)}
        RenderFields={RenderFields}
        type_lookup={{rich_text: EditorInput}}
        onChange={set_form_data}
      />
    </div>
  )
}

export default WithContext(withRouter(Create))
