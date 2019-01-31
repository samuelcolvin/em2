import React from 'react'
import {
  Col,
  Row,
  ButtonGroup,
    Button
} from 'reactstrap'
import WithContext from '../lib/context'
import {Form} from '../lib/form'

const fields = {
  subject: {required: true, max_length: 63},
  message: {required: true, type: 'textarea', max_length: 10000, inputClassName: 'h-150'},
  publish: {title: 'Send Immediately', type: 'bool', className: 'd-none'},
  participants: {type: 'participants'},
}

const RenderFields = ({fields, RenderField}) => (
  <Row>
    <Col md="8">
      <RenderField field={fields.subject}/>
      <RenderField field={fields.message}/>
      <RenderField field={fields.publish}/>
    </Col>
    <Col md="4">
      <RenderField field={fields.participants}/>
    </Col>
  </Row>
)

const FormButtons = ({state, form_props}) => (
  <Row>
    <Col md="8" className="text-right">
      <ButtonGroup className="flex-row-reverse">

        <Button type="submit" color="primary" disabled={state.disabled} onClick={() => form_props.set_publish(true)}>
          Send
        </Button>

        <Button type="submit" color="primary" disabled={state.disabled} onClick={() => form_props.set_publish(false)}>
          Save Draft
        </Button>

        <Button type="button" color="secondary" disabled={state.disabled} onClick={form_props.cancel}>
          Cancel
        </Button>
      </ButtonGroup>
    </Col>
  </Row>
)


class Create extends React.Component {
  state = {form_data: {}}

  set_publish (publish) {
    const form_data = Object.assign({}, this.state.form_data, {publish})
    this.setState({form_data})
  }

  render () {
    return (
      <div className="box create-conv">
        <Form fields={fields}
              form_data={this.state.form_data}
              function="create-conversation"
              Buttons={FormButtons}
              cancel={this.props.history.goBack}
              show_cancel={false}
              set_publish={this.set_publish.bind(this)}
              RenderFields={RenderFields}
              onChange={form_data => this.setState({form_data})}/>
      </div>
    )
  }
}

export default WithContext(Create)
