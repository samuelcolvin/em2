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
      this.state = {
        shown: this.path_match(),
      }
      this.change_handlers = []
    }

    path_match = () => this.regex.test(this.props.location.pathname)

    parent_uri = () => {
      if (this.props.parent_uri) {
        return this.props.parent_uri
      } else {
        return this.props.location.pathname.replace(this.regex, '')
      }
    }

    setState (s) {
      return new Promise(resolve => {
        super.setState(s, resolve)
      })
    }

    componentDidMount () {
      this.toggle(null, this.path_match())
    }

    toggle = (r, shown) => {
      if (shown !== this.state.shown) {
        shown = Boolean(shown)
        this.setState({shown})
        this.change_handlers.map(h => h({response: r || null, shown, modal: this}))
        if (!shown) {
          const parent_uri = this.parent_uri()
          this.props.history.replace(parent_uri + (r && r.pk ? `${r.pk}/` : ''))
        }
      }
    }

    componentDidUpdate (prevProps) {
      if (this.props.location.pathname !== prevProps.location.pathname) {
        this.toggle(null, this.path_match())
      }
    }

    register_change_handler = h => {
      this.change_handlers.push(h)
      return () => {
        this.change_handlers = this.change_handlers.filter(h_ => h_ !== h)
      }
    }

    render () {
      return (
        <Modal isOpen={this.state.shown} toggle={() => this.toggle()}
               size={this.props.size}
               className={this.props.className}>
          <ModalHeader toggle={() => this.toggle()}>
            {this.props.title}
            <span id="modal-title"/>
          </ModalHeader>
          <WrappedComponent
            {...this.props}
            done={this.toggle}
            modal_shown={this.state.shown}
            register_change_handler={this.register_change_handler}
            form_body_class="modal-body"
            form_footer_class="modal-footer"/>
        </Modal>
      )
    }
  }
  AsModal.displayName = `AsModal(${get_component_name(WrappedComponent)})`
  return WithContext(withRouter(AsModal))
}
