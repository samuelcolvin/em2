import React from 'react'
import {withRouter} from 'react-router-dom'
import {WithContext, Loading} from 'reactstrap-toolbox'
import {ConvList} from './List'

class ConvListView extends React.Component {
  state = {query: ''}

  componentDidMount () {
    this.mounted = true
    this.update()
  }

  componentWillUnmount () {
    this.mounted = false
  }

  componentDidUpdate (prevProps) {
    if (this.props.location !== prevProps.location) {
      this.update()
    }
  }

  setState (state, callback) {
    this.mounted && super.setState(state, callback)
  }

  update = async () => {
    if (this.props.ctx.user && this.mounted) {
      const query = decodeURI(this.props.location.search.substr(1))
      if (query.length < window.logic.search.min_length) {
        this.props.history.push('/')
      } else {
        this.props.ctx.setTitle(`Search: ${query}`)
        this.props.ctx.setMenuItem('search')
        this.setState({conversations: await window.logic.search.search(query), query})
      }
    }
  }

  render () {
    if (!this.state.conversations) {
      return <Loading/>
    }
    const c = this.state.conversations.length
    if (c === 0) {
      return (
        <div className="text-muted text-center h5 pt-3 pb-4">
          No Conversations match the search "{this.state.query}"
        </div>
      )
    }
    const user_email = this.props.ctx.user && this.props.ctx.user.email
    return (
      <div>
        <div className="text-muted h6 pb-1">
          {c} search result{c === 1 ? '' : 's'} for "{this.state.query}"
        </div>
        <div className="box conv-list">
          <ConvList conversations={this.state.conversations} user_email={user_email}/>
        </div>
      </div>
    )
  }
}

export default withRouter(WithContext(ConvListView))
