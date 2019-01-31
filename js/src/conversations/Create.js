import React from 'react'
import {
  Col,
  Row,
  ButtonGroup,
    Button
} from 'reactstrap'
import WithContext from '../lib/context'
import {Form} from '../lib/form'

const fields = [
  {name: 'subject', required: true, max_length: 63},
  {name: 'message', required: true, type: 'textarea', max_length: 10000, inputClassName: 'h-150'},
  {name: 'publish', title: 'Send Immediately', type: 'bool', className: 'd-none'},
]

const FormButtons = ({state, form_props}) => (
  <div className="text-right">
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
  </div>
)

class Create extends React.Component {
  constructor (props) {
    super(props)
    this.state = {form_data: {}}
  }

  set_publish (publish) {
    const form_data = Object.assign({}, this.state.form_data, {publish})
    this.setState({form_data})
  }

  render () {
    return (
      <Row className="box create-conv">
        <Col md="9">
          <Form fields={fields}
                form_data={this.state.form_data}
                function="create-conversation"
                Buttons={FormButtons}
                cancel={this.props.history.goBack}
                show_cancel={false}
                set_publish={this.set_publish.bind(this)}
                onChange={form_data => this.setState({form_data})}/>
        </Col>
      </Row>
    )
  }
}

export default WithContext(Create)
