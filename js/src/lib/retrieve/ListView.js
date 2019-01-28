import React from 'react'
import {Link} from 'react-router-dom'
import {withRouter} from 'react-router-dom'
import {as_title} from '../index'
import {Loading} from '../Errors'
import Buttons from './Buttons'
import RetrieveWrapper from './RetrieveWrapper'

const ListViewRender = ({...props}) => {
  const no_items_found = props.no_items_found || `No ${as_title(props.item_name || 'Items')} found`
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
      </div>
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
    state['pages'] > 1 ? (
      <nav key="p" aria-label="Page navigation example">
        <ul className="pagination justify-content-center">
          {[...Array(state['pages']).keys()].map(i => i + 1).map(p => (
            <li key={p} className={'page-item' + (p === current_page ? ' active' : '')}>
              <Link className="page-link" to={`?page=${p}`}>{p}</Link>
            </li>
          ))}
        </ul>
      </nav>
    ) : null,
    <div key="e">
      {Extra && <Extra/>}
    </div>
  ]
}

class ListView extends React.Component {
  constructor (props) {
    super(props)
    this.get_page = this.get_page.bind(this)
    this.get_uri = this.get_uri.bind(this)
  }

  get_page () {
    const m = this.props.location.search.match(/page=(\d+)/)
    return m ? parseInt(m[1]) : 1
  }

  get_uri () {
    return `${this.props.root}?page=${this.get_page()}`
  }

  render () {
    return <RetrieveWrapper {...this.props}
                            get_uri={this.get_uri}
                            get_page={this.get_page}
                            RenderChild={ListViewRender}/>
  }
}

export default withRouter(ListView)
