import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {withRouter} from 'react-router-dom'
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
  // TODO include read notifications, use first name not addr
  return conversations.map((conv, i) => (
    <div key={i}>
      <Link to={`/${conv.key.substr(0, 10)}/`}>
        <div className="subject">{conv.details.sub}</div>
        <div>
          {!conv.publish_ts && <span className="badge badge-dark mr-2">Draft</span>}
          <span className="body">
            {conv.details.email === user_email ? 'you' : conv.details.email}: {conv.details.body}
          </span>
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

const Paginate = ({current, onClick, state}) => (
  <nav>
    <ul className="pagination">
      <li className={`page-item${current === 1 ? ' disabled' : ''}`}>
        <Link className="page-link" onClick={onClick} to={`?page=${current - 1}`}>&laquo;</Link>
      </li>
      {[...Array(state.pages || current).keys()].map(i => i + 1).map(p => (
        <li key={p} className={`page-item${p === current ? ' active' : ''}`}>
          <Link className="page-link" onClick={onClick} to={`?page=${p}`}>{p}</Link>
        </li>
      ))}
      <li className={`page-item${state.more_pages ? '' : ' disabled'}`}>
        <Link className="page-link" onClick={onClick} to={`?page=${current + 1}`}>&raquo;</Link>
      </li>
    </ul>
  </nav>
)

const get_page = s => {
  const m = s.match(/page=(\d+)/)
  return m ? parseInt(m[1]) : 1
}

class ConvListView extends React.Component {
  state = {more_pages: true}

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

  get_page = () => get_page(this.props.location.search)

  on_pagination_click = async e => {
    const link = e.target.getAttribute('href')
    e.preventDefault()
    const next_page = get_page(link)
    if (next_page === this.get_page()) {
      return
    }
    const r = await this.props.ctx.worker.call('list-conversations', {page: next_page})
    if (r.conversations.length) {
      this.setState(r)
      this.props.history.push(link)
    } else {
      this.props.ctx.setMessage({icon: 'times', message: 'No more conversations found'})
      this.setState({more_pages: false})
    }
  }

  render () {
    const user_email = this.props.ctx.user && this.props.ctx.user.email
    return (
      <div>
        <div className="box conv-list">
          <ConvList conversations={this.state && this.state.conversations} user_email={user_email}/>
        </div>
        <div className="d-flex justify-content-center">
          <Paginate current={this.get_page()} onClick={this.on_pagination_click} state={this.state}/>
        </div>
      </div>
    )
  }
}

export default withRouter(WithContext(ConvListView))
