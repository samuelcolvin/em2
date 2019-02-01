import React from 'react'
import {render_key, render_value} from './Detail'
import {withRouter} from 'react-router-dom'
import WithContext from '../context'
import {conn_status} from '../requests'

class RetrieveWrapper extends React.Component {
  constructor (props) {
    super(props)
    this.render_key = this.render_key.bind(this)
    this.render_value = this.render_value.bind(this)
    this.update = this.update.bind(this)
    this.state = {}
    this.formats = props.formats || {}
  }

  componentDidMount () {
    this.update()
  }

  componentDidUpdate (prevProps) {
    const [l, pl] = [this.props.location, prevProps.location]
    if (l.pathname + l.search !== pl.pathname + pl.search) {
      this.update()
    }
  }

  async update () {
    const r = await this.props.ctx.worker.call(this.props.function, this.props.get_args())
    if (r === conn_status.not_connected) {
      this.props.ctx.setConnectionStatus(r)
    } else if (r === conn_status.unauthorised) {
      this.props.history.push('/login/')
    } else {
      this.props.ctx.setConnectionStatus(conn_status.connected)  // TODO remove once we have websockets to do the same
      this.props.ctx.setTitle(this.props.title)
      this.setState(this.props.transform ? this.props.transform(r) : r)
    }
  }

  render_key (key) {
    return render_key(this.formats, key)
  }

  render_value (item, key) {
    return render_value(this.formats, item, key)
  }

  render () {
    const Render = this.props.Render
    return (
      <Render {...this.props} state={this.state} formats={this.formats}
              render_key={this.render_key} render_value={this.render_value}/>
    )
  }
}
export default withRouter(WithContext(RetrieveWrapper))
