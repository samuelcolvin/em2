import React from 'react'
import ReactDOM from 'react-dom'
import {
  Button,
  ButtonGroup,
  Modal,
  ModalBody,
  ModalFooter as BsModalFooter,
  ModalHeader,
} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import WithContext from './context'
import {as_title, get_component_name} from './index'
import Detail, {render} from './retrieve/Detail'

export const ModalFooter = ({done, disabled, label, cancel_disabled}) => (
  <BsModalFooter>
    <ButtonGroup>
      <Button type="button" color="secondary" onClick={() => done()} disabled={cancel_disabled}>
        Cancel
      </Button>
      <Button type="submit" color="primary" disabled={disabled}>
        {label || 'Book'}
      </Button>
    </ButtonGroup>
  </BsModalFooter>
)

export const InfoModal = ({onClose, isOpen, title, fields, extra_fields, object, children}) => {
  const e_fields = Object.assign({}, extra_fields)
  return (
    <Modal isOpen={isOpen} toggle={onClose} size="lg">
      <ModalHeader toggle={onClose}>{title}</ModalHeader>
      <ModalBody>
        {children}
        {object && (
          <div>
            {Object.entries(fields).map(([k, value]) => (
              <Detail k={k} name={value.title || as_title(k)}>
                {value.render ? value.render(object[k], object) : object[k]}
              </Detail>
            ))}
            {Object.entries(object.extra || []).map(([k, value]) => (
              <Detail key={`extra_${k}`} name={(e_fields[k] && e_fields[k].title) || as_title(k)}>
                {(e_fields[k] && e_fields[k].render && e_fields[k].render(value, object)) || render(value)}
              </Detail>
            ))}
          </div>
        )}
      </ModalBody>
      <BsModalFooter>
        <Button color="secondary" onClick={onClose}>Close</Button>
      </BsModalFooter>
    </Modal>
  )
}

export const SetModalTitle = ({children}) => {
  const el = document.getElementById('modal-title')
  if (children && el) {
    return ReactDOM.createPortal(children, el)
  } else {
    return null
  }
}

export default function AsModal (WrappedComponent) {
  class AsModal extends React.Component {
    constructor (props) {
      super(props)
      this.regex = props.regex || /modal\/$/
      this.path_match = () => this.regex.test(this.props.location.pathname)
      this.state = {
        shown: this.path_match(),
      }
      this.toggle = this.toggle.bind(this)
      this.toggle_handlers = []
    }

    toggle (r) {
      const shown_new = !this.state.shown
      this.setState({
        shown: shown_new,
      })
      this.toggle_handlers.map(h => h(r))
      if (!this.state.shown_new) {
        this.props.history.replace(this.props.parent_uri + (r && r.pk ? `${r.pk}/`: ''))
      }
    }

    componentDidUpdate (prevProps) {
      if (this.props.location !== prevProps.location) {
        this.setState({
          shown: this.path_match(),
        })
      }
    }

    render () {
      return (
        <Modal isOpen={this.state.shown} toggle={() => this.toggle()} size="lg">
          <ModalHeader toggle={() => this.toggle()}>
            {this.props.title}<span id="modal-title"/>
          </ModalHeader>
          <WrappedComponent
            {...this.props}
            done={this.toggle}
            register_toggle_handler={h => this.toggle_handlers.push(h)}
            form_body_class="modal-body"
            form_footer_class="modal-footer"/>
        </Modal>
      )
    }
  }
  AsModal.displayName = `AsModal(${get_component_name(WrappedComponent)})`
  return WithContext(withRouter(AsModal))
}
