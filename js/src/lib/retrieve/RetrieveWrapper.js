import React from 'react'
import {render_key, render_value} from './Detail'
import {withRouter} from 'react-router-dom'
import WithContext from '../context'

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
    const uri = this.props.get_uri ? this.props.get_uri() : this.props.root
    let r = await this.props.ctx.requests.get(uri)
    this.setState(this.props.transform ? this.props.transform(r) : r.data)
  }

  render_key (key) {
    return render_key(this.formats, key)
  }

  render_value (item, key) {
    return render_value(this.formats, item, key)
  }

  render () {
    const RenderChild = this.props.RenderChild
    return (
      <RenderChild {...this.props} state={this.state} formats={this.formats}
                   render_key={this.render_key} render_value={this.render_value}/>
    )
  }
}
export default withRouter(WithContext(RetrieveWrapper))
