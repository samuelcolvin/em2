import React from 'react'
import {Link} from 'react-router-dom'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {Button} from 'reactstrap'
import {as_title} from '../index'

const Dash = () => <span>&mdash;</span>

export const render = v => {
  if (typeof v === 'boolean') {
    return <FontAwesomeIcon icon={v ? 'check' : 'times'}/>
  } else if ([null, undefined].includes(v)) {
    return <Dash/>
  } else if (typeof v === 'object') {
    if (Object.keys(v).includes('$$typeof')) {
      return v
    } else {
      return JSON.stringify(v)
    }
  } else {
    return v
  }
}

export const render_key = (formats, key) => {
  const fmt = formats[key]
  if (fmt && fmt.title) {
    return fmt.title
  }
  return as_title(key)
}

export const render_value = (formats, item, key) => {
  const fmt = formats[key]
  const v = item[key]
  if (fmt && fmt.render) {
    return fmt.render(v, item)
  } else {
    return render(v)
  }
}

export default ({name, wide, edit_link, children}) => (
  <div className={`item-detail${wide ? ' wide' : ''}`}>
    <div className="key">
      {name}
      {edit_link && <Button tag={Link} to={edit_link} size="sm" className="ml-2">
        <FontAwesomeIcon icon="pencil-alt" className="mr-1"/>
        Edit {name}
      </Button>}
    </div>
    <div className="value">
      {render(children)}
    </div>
  </div>
)
