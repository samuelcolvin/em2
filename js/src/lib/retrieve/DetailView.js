import React from 'react'
import {Loading} from '../Errors'
import Buttons from './Buttons'
import RetrieveWrapper from './RetrieveWrapper'
import Detail from './Detail'
import {withRouter} from 'react-router-dom'

const ignored_keys = ['id', 'name']

const DetailDefaultRender = ({...props}) => {
  const Extra = props.Extra
  const state = props.state
  const formats = props.formats

  if (!state.item) {
    return <Loading/>
  }
  const keys = (
    Object.keys(state.item)
    .filter(k => !ignored_keys.includes(k) && formats[k] !== null)
    .map(k => ({key: k, fmt: formats[k] || {}}))
    .sort((a, b) => (a.fmt.wide || 0) - (b.fmt.wide || 0))
    .sort((a, b) => (a.fmt.index || 0) - (b.fmt.index || 0))
  )
  const pre = props.pre
  return [
    <Buttons key="b" buttons={state.buttons}/>,
    state.item.name && <h1 key="t">{state.item.name}</h1>,
    pre ? <div key="p">{pre}</div> : null,
    <div key="d" className="mb-4">
      {keys.map(k => (
        <Detail key={k.key} name={props.render_key(k.key)} wide={Boolean(k.fmt.wide)} edit_link={k.fmt.edit_link}>
          {props.render_value(state.item, k.key)}
        </Detail>
      ))}
    </div>,
    <div key="e">
      {Extra && <Extra/>}
    </div>,
  ]
}

const DetailView = ({...props}) => {
  const get_args = () => props.match.params
  const Render = props.Render || DetailDefaultRender
  return <RetrieveWrapper {...props} get_args={get_args} Render={Render}/>
}

export default withRouter(DetailView)
