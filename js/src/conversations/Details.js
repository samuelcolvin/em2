import React from 'react'
// import {Link} from 'react-router-dom'
// import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
// import {format_ts} from '../lib'
import {Col, Row} from 'reactstrap'
import {withRouter} from 'react-router-dom'
import {Loading} from '../lib/Errors'
import WithContext from '../lib/context'
import {format_ts} from '../lib'

const Message = ({msg}) => {
  // console.log(msg)
  return (
    <div className="box">
      <div>{format_ts(msg.created)}</div>
      <div>{msg.body}</div>
      {/*<pre>{JSON.stringify(msg, null, 2)}</pre>*/}
    </div>
  )
}

class ConvDetailsView extends React.Component {
  async componentDidMount () {
    this.mounted = true
    this.update()
    this.remove_listener = this.props.ctx.worker.add_listener('change', this.update)
  }

  componentWillUnmount () {
    this.mounted = false
    this.remove_listener()
  }

  setState (state, callback) {
    this.mounted && super.setState(state, callback)
  }

  update = async () => {
    const state = await this.props.ctx.worker.call('get-conversation', this.props.match.params)
    this.props.ctx.setTitle(state.subject)
    this.setState(state)
  }

  render () {
    if (!this.state) {
      return <Loading/>
    }
    console.log(this.state)
    return (
      <Row>
        <Col md="8">
          {this.state.messages.map(msg => <Message msg={msg} key={msg.ref}/>)}
        </Col>
        <Col md="4">
          <div className="box">
            {Object.keys(this.state.participants).map((p, i) => (
                <div key={i}>{p}</div>
            ))}
          </div>
        </Col>
      </Row>
    )
  }
}

export default withRouter(WithContext(ConvDetailsView))
