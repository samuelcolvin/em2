import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {withRouter} from 'react-router-dom'
import {Paginate} from '../lib/retrieve/ListView'
import {format_ts} from '../lib'
import {Loading} from '../lib/Errors'
import WithContext from '../lib/context'

const ConvList = ({conversations, user_email}) => {
  if (!conversations) {
    return <Loading/>
  } else if (conversations.length === 0) {
    return (
      <div key="f" className="text-muted text-center h5 pt-3 pb-4">
        No Conversations found
      </div>
    )
  }
  // TODO include read notifications, popovers, use first name not addr
  return conversations.map((conv, i) => (
    <div key={i}>
      <Link to={`/${conv.key.substr(0, 10)}/`}>
        <div className="subject">{conv.details.sub}</div>
        <div className="body">
          {conv.details.email === user_email ? 'you' : conv.details.email}: {conv.details.body}
        </div>

        <div>
          <span className="icon">
            <FontAwesomeIcon icon="comment"/> {conv.details.msgs}
          </span>
          <span className="icon">
            <FontAwesomeIcon icon="users"/> {conv.details.prts}
          </span>
          <span>
            {format_ts(conv.updated_ts)}
          </span>
        </div>
      </Link>
    </div>
  ))
}

class ConvListView extends React.Component {
  async componentDidMount () {
    this.mounted = true
    this.props.ctx.setTitle('Conversations')
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
    this.setState(await this.props.ctx.worker.call('list-conversations', {page: this.get_page()}))
  }

  get_page = () => {
    const m = this.props.location.search.match(/page=(\d+)/)
    return m ? parseInt(m[1]) : 1
  }

  render () {
    const user_email = this.props.ctx.user && this.props.ctx.user.email
    return (
      <div className="box conv-list">
        <ConvList conversations={this.state && this.state.conversations} user_email={user_email}/>
        <Paginate pages={this.state && this.state['pages']} current_page={this.get_page()}/>
      </div>
    )
  }
}

export default withRouter(WithContext(ConvListView))
