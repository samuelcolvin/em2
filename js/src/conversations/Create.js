import React from 'react'
import {withRouter} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
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

const FormButtons = ({state, form_props, submit, setField}) => {
  const pub_submit = async publish => {
    await setField('publish', publish)
    submit()
  }

  const on_keydown = e => {
    if (e.key === 'Enter' && e.ctrlKey) {
      pub_submit(false)
    }
  }

  React.useEffect(() => {
    window.addEventListener('keydown', on_keydown)
    return () => window.removeEventListener('keydown', on_keydown)
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Row>
      <Col md="8" className="text-right">
        <ButtonGroup className="flex-row-reverse">

          <Button color="primary" disabled={state.disabled} onClick={() => pub_submit(true)}>
            <FontAwesomeIcon icon={fas.faPaperPlane} className="mr-1"/>
            Send
          </Button>

          <Button color="primary" disabled={state.disabled} onClick={() => pub_submit(false)}>
            Save Draft
          </Button>

          <Button type="button" color="secondary"
                  disabled={state.disabled}
                  onClick={form_props.cancel}>
            Cancel
          </Button>
        </ButtonGroup>
      </Col>
    </Row>
  )
}


const Create = ({ctx, history}) => {
  const [form_data, set_form_data] = React.useState(0)
  React.useEffect(() => {
    ctx.setMenuItem('create')
    ctx.setTitle('Compose Conversation')
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="box create-conv">
      <Form
        fields={fields}
        form_data={form_data}
        function={window.logic.conversations.create}
        Buttons={FormButtons}
        RenderFields={RenderFields}
        submitted={r => history.push(`/${r.data.key}/`)}
        type_lookup={{participants: ParticipantsInput}}
        onChange={set_form_data}
      />
    </div>
  )
}

export default WithContext(withRouter(Create))
