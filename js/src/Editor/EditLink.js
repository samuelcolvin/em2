import React from 'react'
import ReactDOM from 'react-dom'
import {
  InputGroup,
  Input,
  InputGroupAddon,
  Button,
  Modal,
  ModalHeader,
} from 'reactstrap'


export default class EditLink extends React.Component {
  // state = {link: null}
  //
  // componentWillUpdate(nextProps) {
  //   if (this.state.link === null && nextProps.link) {
  //     this.setState({link: nextProps.link})
  //   }
  // }

  close = () => this.props.update_link(null)

  submit = async e => {
    e.preventDefault()
    console.log(this.state)
    // this.close()
    // await this.props.set_subject(this.state.subject, this.follows_id)
    // this.props.done()
  }

  render () {
    return (
      <Modal isOpen={this.props.link !== null} toggle={this.close} className="simplified-modal">
        <ModalHeader toggle={this.close}>Edit Link</ModalHeader>
        <form className="modal-body" onSubmit={this.submit}>
          <InputGroup>
            <Input
              type="url"
              required={true}
              placeholder="link URL..."
              value={this.props.link}
              onChange={e => this.props.update_link(e.target.value)}
            />
            <InputGroupAddon addonType="append">
              <Button color="primary" type="submit">
                Update Link
              </Button>
            </InputGroupAddon>
          </InputGroup>
        </form>
      </Modal>
    )
  }

  // render () {
  //   return ReactDOM.createPortal(
  //     this.render_modal(),
  //     document.getElementById('modal')
  //   )
  // }
}
