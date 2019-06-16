import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {withRouter} from 'react-router-dom'
import {WithContext, Loading} from 'reactstrap-toolbox'
import {format_ts} from '../utils/dt'

export const ConvList = ({conversations, user_email}) => conversations.map((conv, i) => (
  <Link key={i} to={`/${conv.key.substr(0, 10)}/`} className={conv.seen ? 'seen' : ''}>
    <div className="subject">{conv.details.sub}</div>
    <div className="summary">
      <span className="body">
        {conv.details.email === user_email ? 'you' : conv.details.email}: {conv.details.prev}
      </span>
    </div>

    <div className="details">
      <span className="d-none d-lg-inline-block">
        <span className="icon">
          <FontAwesomeIcon icon={fas.faComment}/> {conv.details.msgs}
        </span>
        <span className="icon">
          <FontAwesomeIcon icon={fas.faUsers}/> {conv.details.prts}
        </span>
      </span>
      <span>
        {format_ts(conv.updated_ts)}
      </span>
    </div>
  </Link>
))

const Paginate = ({current, onClick, pages}) => (
  pages === 1 ? null : (
      <nav>
        <ul className="pagination">
          <li className={`page-item${current === 1 ? ' disabled' : ''}`}>
            <Link className="page-link" onClick={onClick} to={`?page=${current - 1}`}>&laquo;</Link>
          </li>
          {[...Array(pages).keys()].map(i => i + 1).map(p => (
            <li key={p} className={`page-item${p === current ? ' active' : ''}`}>
              <Link className="page-link" onClick={onClick} to={`?page=${p}`}>{p}</Link>
            </li>
          ))}
          <li className={`page-item${current === pages ? ' disabled' : ''}`}>
            <Link className="page-link" onClick={onClick} to={`?page=${current + 1}`}>&raquo;</Link>
          </li>
        </ul>
      </nav>
    )
)

const get_page = s => {
  const m = s.match(/page=(\d+)/)
  return m ? parseInt(m[1]) : 1
}

class ConvListView extends React.Component {
  state = {}

  async componentDidMount () {
    this.mounted = true
    this.update()
    this.remove_listener = window.logic.add_listener('change', this.update)
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
      this.setState({
        conversations: await window.logic.conversations.list({page: this.get_page(), flag}),
        pages: window.logic.conversations.pages(flag),
      })
    }
  }

  get_page = () => get_page(this.props.location.search)

  on_pagination_click = async e => {
    const link = e.target.getAttribute('href')
    const page = get_page(link)
    if (page === this.get_page()) {
      return
    }
    e.preventDefault()
    const conversations = await window.logic.conversations.list({page, flag: this.conv_flag()})
    this.setState({conversations})
    this.props.history.push(link)
  }

  render () {
    if (!this.state.conversations) {
      return <Loading/>
    } else if (this.state.conversations.length === 0) {
      return (
        <div className="text-muted text-center h5 pt-3 pb-4">
          No Conversations found
        </div>
      )
    }
    const user_email = this.props.ctx.user && this.props.ctx.user.email
    return (
      <div>
        <div className="box conv-list">
          <ConvList conversations={this.state.conversations} user_email={user_email}/>
        </div>
        <div className="d-flex justify-content-center">
          <Paginate current={this.get_page()} onClick={this.on_pagination_click} pages={this.state.pages}/>
        </div>
      </div>
    )
  }
}

export default withRouter(WithContext(ConvListView))
