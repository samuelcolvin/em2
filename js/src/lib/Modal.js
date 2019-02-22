import React from 'react'
import {
  Modal,
  ModalHeader,
} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import WithContext from './context'
import {get_component_name} from './index'


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
