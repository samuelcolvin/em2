import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {withRouter} from 'react-router-dom'
import {WithContext, Loading, message_toast} from 'reactstrap-toolbox'
import {format_ts} from '../utils/dt'

const ConvList = ({conversations, user_email}) => conversations.map((conv, i) => (
  <Link key={i} to={`/${conv.key.substr(0, 10)}/`} className={conv.seen ? 'seen' : ''}>
    <div className="subject">{conv.details.sub}</div>
    <div className="summary">
      {!conv.publish_ts && <span className="badge badge-dark mr-2">Draft</span>}
      <span className="body">
        {conv.details.email === user_email ? 'you' : conv.details.email}: {conv.details.prev}
      </span>
    </div>

    <div className="details">
      <span className="icon">
        <FontAwesomeIcon icon={fas.faComment}/> {conv.details.msgs}
      </span>
      <span className="icon">
        <FontAwesomeIcon icon={fas.faUsers}/> {conv.details.prts}
      </span>
      <span>
        {format_ts(conv.updated_ts)}
      </span>
    </div>
  </Link>
))

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
    this.update()
    this.remove_listener = this.props.ctx.worker.add_listener('change', this.update)
  }

  componentDidUpdate (prevProps) {
    if (this.props.location !== prevProps.location) {
      this.update()
    }
  }

  componentWillUnmount () {
    this.mounted = false
    this.remove_listener && this.remove_listener()
  }

  setState (state, callback) {
    this.mounted && super.setState(state, callback)
  }

  conv_flag = () => this.props.match.params.flag || 'inbox'

  update = async () => {
    if (this.props.ctx.user) {
      this.props.ctx.setTitle(this.props.ctx.user.name) // TODO add the number of unseen messages
      const flag = this.conv_flag()
      this.props.ctx.setMenuItem(flag)
      const args = {page: this.get_page(), flag}
      this.setState(await this.props.ctx.worker.call('list-conversations', args))
    }
  }

  get_page = () => get_page(this.props.location.search)

  on_pagination_click = async e => {
    const link = e.target.getAttribute('href')
    e.preventDefault()
    const page = get_page(link)
    if (page === this.get_page()) {
      return
    }
    const r = await this.props.ctx.worker.call('list-conversations', {page, state: this.conv_state()})
    if (r.conversations.length) {
      this.setState(r)
      this.props.history.push(link)
    } else {
      message_toast({icon: 'times', title: 'No more Conversations', message: 'No more Conversations found'})
      this.setState({more_pages: false})
    }
  }

  render () {
    const user_email = this.props.ctx.user && this.props.ctx.user.email
    const conversations = this.state && this.state.conversations
    if (!conversations) {
      return <Loading/>
    } else if (conversations.length === 0) {
      return (
        <div key="f" className="text-muted text-center h5 pt-3 pb-4">
          No Conversations found
        </div>
      )
    }
    return (
      <div>
        <div className="box conv-list">
          <ConvList conversations={conversations} user_email={user_email}/>
        </div>
        <div className="d-flex justify-content-center">
          <Paginate current={this.get_page()} onClick={this.on_pagination_click} state={this.state}/>
        </div>
      </div>
    )
  }
}

export default withRouter(WithContext(ConvListView))
