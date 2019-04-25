import React from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {
  Col,
  Row,
  ButtonGroup,
  Button,
} from 'reactstrap'
import {WithContext, Form} from 'reactstrap-toolbox'
import ParticipantsInput from './ParticipantsInput'

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

class FormButtons extends React.Component {
  submit = async publish => {
    await this.props.setField('publish', publish)
    this.props.submit()
  }

  on_keydown = e => {
    if (e.key === 'Enter' && e.ctrlKey) {
      this.submit(false)
    }
  }

  componentDidMount () {
    document.addEventListener('keydown', this.on_keydown)
  }

  componentWillUnmount (){
    document.removeEventListener('keydown', this.on_keydown)
  }

  render () {
    return (
      <Row>
        <Col md="8" className="text-right">
          <ButtonGroup className="flex-row-reverse">

            <Button color="primary" disabled={this.props.state.disabled} onClick={() => this.submit(true)}>
              <FontAwesomeIcon icon="paper-plane" className="mr-1"/>
              Send
            </Button>

            <Button color="primary" disabled={this.props.state.disabled} onClick={() => this.submit(false)}>
              Save Draft
            </Button>

            <Button type="button" color="secondary"
                    disabled={this.props.state.disabled}
                    onClick={this.props.form_props.cancel}>
              Cancel
            </Button>
          </ButtonGroup>
        </Col>
      </Row>
    )
  }
}


class Create extends React.Component {
  state = {form_data: {}}

  submitted (r) {
    this.props.history.push(`/${r.data.key}/`)
  }

  componentDidMount () {
    this.props.ctx.setTitle('Compose Conversation')
  }

  render () {
    return (
      <div className="box create-conv">
        <Form fields={fields}
              form_data={this.state.form_data}
              function="create-conversation"
              Buttons={FormButtons}
              RenderFields={RenderFields}
              submitted={this.submitted.bind(this)}
              type_lookup={{participants: ParticipantsInput}}
              onChange={form_data => this.setState({form_data})}/>
      </div>
    )
  }
}

export default WithContext(Create)
