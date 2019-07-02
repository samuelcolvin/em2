import React from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {Button} from 'reactstrap'

export const T = {
  para: 'paragraph',
  bold: 'bold',
  italic: 'italic',
  underlined: 'underlined',
  deleted: 'deleted',
  link: 'link',
  heading: 'heading',
  code: 'code',
  code_line: 'code-line',
  bullets: 'bulleted-list',
  numbers: 'ordered-list',
  list_item: 'list-item',
  block_quote: 'block-quote',
  hr: 'horizontal-rule',
}
export const is_list_type = t => t === T.numbers || t=== T.bullets
export const raw_empty = {
  object: 'value',
  document: {
    object: 'document',
    data: {},
    nodes: [
      {
        object: 'block',
        type: 'paragraph',
        data: {},
        nodes: [{object: 'text', text: '', marks: []}],
      },
    ],
  },
}

const fa_name = s => 'fa' + s.charAt(0).toUpperCase() + s.slice(1).replace('-', '')

const mark_active = (main, type) => main.props.value.activeMarks.some(mark => mark.type === type)

export const MarkButton = ({main, type, title, onMouseDown = null, icon = null}) => (
  <Button title={title}
          color="light-border"
          onMouseDown={e => (onMouseDown || main.toggle_mark)(e, type)}
          active={mark_active(main, type)}
          type="button"
          tabIndex="-1"
          disabled={main.disable_button(type, 'mark')}>
    <FontAwesomeIcon icon={icon || fas[ fa_name(type)]}/>
  </Button>
)

export const BlockButton = ({main, type, title, onMouseDown = null, icon = null}) => (
  <Button title={title}
          color="light-border"
          onMouseDown={e => (onMouseDown || main.toggle_block)(e, type)}
          active={main.block_active(type)}
          type="button"
          tabIndex="-1"
          disabled={main.disable_button(type, 'block')}>
    <FontAwesomeIcon icon={icon || fas[fa_name(type)]}/>
  </Button>
)

export const render_block = (props, editor, next) => {
  const {attributes, children, node} = props

  switch (node.type) {
    case T.para:
      return <p {...attributes}>{children}</p>
    case T.block_quote:
      return <blockquote {...attributes}>{children}</blockquote>
    case T.bullets:
      return <ul {...attributes}>{children}</ul>
    case T.numbers:
      return <ol {...attributes}>{children}</ol>
    case 'todo-list':
      return <ul {...attributes}>{children}</ul>
    case 'table':
      return (
        <table className="table table-striped" {...attributes}>
          <tbody>
            {children}
          </tbody>
        </table>
      )
    case 'table-row':
      return <tr {...attributes}>{children}</tr>
    case 'table-head':
      return <th {...attributes}>{children}</th>
    case 'table-cell':
      return <td {...attributes}>{children}</td>
    case T.list_item:
      return <li {...attributes}>{children}</li>
    case T.hr:
      return <hr/>
    case T.code:
      return <pre><code {...attributes}>{children}</code></pre>
    case 'image':
      return <img src={props.src} title={props.title} alt={props.title} />
    case 'heading1':
      return <h1 {...attributes}>{children}</h1>
    case 'heading2':
      return <h2 {...attributes}>{children}</h2>
    case 'heading3':
      return <h3 {...attributes}>{children}</h3>
    case 'heading4':
      return <h4 {...attributes}>{children}</h4>
    case 'heading5':
      return <h5 {...attributes}>{children}</h5>
    case 'heading6':
      return <h6 {...attributes}>{children}</h6>
    default:
      return next()
  }
}

export const render_inline = ({attributes, children, node}, editor, next) => {
  if (node.type === T.link) {
    return <a href={node.data.get('href')} target="_blank" rel="noopener noreferrer" {...attributes}>{children}</a>
  } else {
    return next()
  }
}

export const render_mark = ({attributes, children, mark, node}, editor, next) => {
  switch (mark.type) {
    case T.bold:
      return <strong {...attributes}>{children}</strong>
    case T.code:
      return <code {...attributes}>{children}</code>
    case T.italic:
      return <em {...attributes}>{children}</em>
    case T.underlined:
      return <u {...attributes}>{children}</u>
    case T.deleted:
    case 'deleted':
      return <del {...attributes}>{children}</del>
    case 'added':
      return <mark {...attributes}>{children}</mark>
    default:
      return next()
  }
}

export const on_enter = (e, editor, next) => {
  const {value} = editor
  const {selection} = value
  const {start, end, isExpanded} = selection
  if (isExpanded) {
    return next()
  }

  const {startBlock} = value
  if (start.offset === 0 && startBlock.text.length === 0) {
    return on_backspace(e, editor, next)
  } else if (end.offset !== startBlock.text.length) {
    return next()
  }

  if (/(heading\d|block-quote)/.test(startBlock.type)) {
    e.preventDefault()
    editor.splitBlock().setBlocks(T.para)
  } else {
    const chars = startBlock.text.slice(0, start.offset).replace(/\s*/g, '')
    if (/^-{3,}$/.test(chars)) {
      editor.setBlocks(T.hr).insertBlock(T.para)
    } else {
      next()
    }
  }
}

export const on_backspace = (e, editor, next) => {
  const {value} = editor
  const {selection, document, startBlock} = value
  if (selection.isExpanded || selection.start.offset !== 0) {
    return next()
  }

  const {type, key} = startBlock
  const prev = document.getPreviousSibling(key)
  if (prev && prev.type === T.hr) {
    editor.removeNodeByKey(prev.key)
    e.preventDefault()
    return
  }

  if (type === T.para) {
    return next()
  }

  e.preventDefault()

  if (type === T.list_item) {
    editor.setBlocks(T.para).unwrapBlock(T.bullets).unwrapBlock(T.numbers)
  } else if (type === T.code_line) {
    editor.setBlocks(T.para).unwrapBlock(T.code)
  } else if (type !== T.para) {
    editor.setBlocks(T.para)
  }
}

export const on_space = (e, editor, next) => {
  const {value} = editor
  const {selection} = value
  if (selection.isExpanded) {
    return next()
  }

  const {startBlock} = value
  const {start} = selection
  const chars = startBlock.text.slice(0, start.offset).replace(/\s*/g, '')
  let type, wrap_type
  if (['*', '-', '+'].includes(chars)) {
    if (startBlock.type === T.list_item) {
      return next()
    }
    type = T.list_item
    wrap_type = T.bullets
  } else if ('1.' === chars) {
    if (startBlock.type === T.list_item) {
      return next()
    }
    type = T.list_item
    wrap_type = T.numbers
  } else if ('>' === chars) {
    type = T.block_quote
  } else if (/^#{1,6}$/.test(chars)) {
    type = `heading${chars.length}`
  } else if ('```' === chars) {
    type = T.code_line
    wrap_type = T.code
  } else {
    return next()
  }
  e.preventDefault()

  editor.setBlocks(type)

  if (wrap_type) {
    editor.wrapBlock(wrap_type)
  }

  editor.moveFocusToStartOfNode(startBlock).delete()
}

export const apply_code_block = editor => {
  editor.setBlocks(T.code_line).unwrapBlock(T.bullets).unwrapBlock(T.numbers).wrapBlock(T.code)

  const {selection} = editor.value
  editor.moveToRangeOfNode(editor.value.startBlock)
    .removeMark(T.bold)
    .removeMark(T.italic)
    .removeMark(T.underlined)
    .removeMark(T.deleted)
    .removeMark(T.code)
    .select(selection)
}
