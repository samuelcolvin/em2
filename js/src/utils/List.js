import React from 'react'
import {Link} from 'react-router-dom'
import {Loading} from 'reactstrap-toolbox'

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

function get_page (s) {
  const m = s.match(/page=(\d+)/)
  return m ? parseInt(m[1]) : 1
}

export default class ListView extends React.Component {
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

  update = async () => {
    if (this.props.ctx.user) {
      this.props.ctx.setTitle(this.props.title) // TODO add the number of unseen messages
      this.props.ctx.setMenuItem(this.props.menu_item)
      this.setState({items: null})
      const {items, pages} = await this.props.list_items(this.get_page())
      this.setState({items, pages})
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
    this.setState({items: null})
    const {items, pages} = await this.props.list_items(this.get_page())
    this.setState({items, pages})
    this.props.history.push(link)
  }

  render () {
    if (!this.state.items) {
      return <Loading/>
    } else if (this.state.items.length === 0) {
      return (
        <div className="text-muted text-center h5 pt-3 pb-4">
          {this.props.none_text || 'No items found'}
        </div>
      )
    }
    const ListRenderer = this.props.render
    return (
      <div className={this.props.className || 'list-view'}>
        <div className="box list-items">
          <ListRenderer items={this.state.items} ctx={this.props.ctx}/>
        </div>
        <div className="d-flex justify-content-center">
          <Paginate current={this.get_page()} onClick={this.on_pagination_click} pages={this.state.pages}/>
        </div>
      </div>
    )
  }
}
