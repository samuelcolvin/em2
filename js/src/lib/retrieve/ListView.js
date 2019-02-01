import React from 'react'
import {Link} from 'react-router-dom'
import {withRouter} from 'react-router-dom'
import {as_title} from '../index'
import {Loading} from '../Errors'
import Buttons from './Buttons'
import RetrieveWrapper from './RetrieveWrapper'

export const Paginate = ({pages, current_page}) => (
  pages > 1 ? (
    <nav aria-label="Page navigation example">
      <ul className="pagination justify-content-center">
        {[...Array(pages).keys()].map(i => i + 1).map(p => (
          <li key={p} className={'page-item' + (p === current_page ? ' active' : '')}>
            <Link className="page-link" to={`?page=${p}`}>{p}</Link>
          </li>
        ))}
      </ul>
    </nav>
  ) : null
)

const DefaultListRender = ({...props}) => {
  const no_items_found = props.no_items_found || `No ${as_title(props.title || 'Items')} found`
  const get_link = props.get_link || (item => `${props.root}${item.id}/`)
  const Extra = props.Extra
  const state = props.state
  if (!state.items) {
    return <Loading/>
  } else if (state.items.length === 0) {
    return [
      <Buttons key="b" buttons={props.buttons}/>,
      <div key="f" className="text-muted text-center h5 mt-4">
        {no_items_found}
      </div>,
      <div key="e">
        {Extra && <Extra/>}
      </div>,
    ]
  }
  const keys = Object.keys(state.items[0])
  keys.includes('id') && keys.splice(keys.indexOf('id'), 1)
  const current_page = props.get_page()
  return [
    <Buttons key="b" buttons={props.buttons}/>,
    <table key="t" className="table dashboard">
      <thead>
        <tr>
          {keys.map((key, i) => (
            <th key={i} scope="col">{props.render_key(key)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {state.items.map((item, i) => (
          <tr key={i}>
            {keys.map((key, j) => (
              j === 0 ? (
                <td key={j}>
                  <Link to={get_link(item)}>{props.render_value(item, key)}</Link>
                </td>
              ) : (
                <td key={j}>{props.render_value(item, key)}</td>
              )
            ))}
          </tr>
        ))}
      </tbody>
    </table>,
    <Paginate key="p" pages={state['pages']} current_page={current_page}/>,
    <div key="e">
      {Extra && <Extra/>}
    </div>,
  ]
}

class ListView extends React.Component {
  constructor (props) {
    super(props)
    this.get_page = this.get_page.bind(this)
    this.get_args = this.get_args.bind(this)
  }

  get_page () {
    const m = this.props.location.search.match(/page=(\d+)/)
    return m ? parseInt(m[1]) : 1
  }

  get_args () {
    return {page: this.get_page()}
  }

  render () {
    const Render = this.props.Render || DefaultListRender
    return <RetrieveWrapper {...this.props}
                            get_args={this.get_args}
                            get_page={this.get_page}
                            Render={Render}/>
  }
}

export default withRouter(ListView)
