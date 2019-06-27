import React from 'react'
import MarkdownSerializer from '@edithq/slate-md-serializer'
import {Editor} from 'slate-react'
import {isKeyHotkey} from 'is-hotkey'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {
  ButtonGroup,
  Button,
} from 'reactstrap'

// value
// onChange

const Serializer = new MarkdownSerializer()

const bold_key = isKeyHotkey('mod+b')
const italic_key = isKeyHotkey('mod+i')
const underline_key = isKeyHotkey('mod+u')
const code_key = isKeyHotkey('mod+`')

const types = {
  para: 'paragraph',
  bullets: 'bulleted-list',
  numbers: 'numbered-list',
  list_item: 'list-item',
  block_quote: 'block-quote',
}
const is_list_type = t => [types.numbers, types.bullets].includes(t)

export default class MessageEditor extends React.Component {
  state = {
    value: Serializer.deserialize(''), // TODO
  }

  has_block = type => this.state.value.blocks.some(node => node.type === type)

  block_active = type => {
    let is_active = this.has_block(type)

    if (is_list_type(type)) {
      const {value: {document, blocks}} = this.state

      if (blocks.size > 0) {
        const parent = document.getParent(blocks.first().key)
        is_active = this.has_block(types.list_item) && parent && parent.type === type
      }
    }
    return is_active
  }

  toggle_mark = (e, type) => {
    e.preventDefault()
    this.editor.toggleMark(type)
  }

  toggle_block = (e, type) => {
    e.preventDefault()
    const {editor} = this
    const {value} = editor
    const {document} = value

    if (is_list_type(type)) {
      // Handle the extra wrapping required for list buttons.
      const isList = this.has_block(types.list_item)
      const isType = value.blocks.some(block => !!document.getClosest(block.key, parent => parent.type === type))

      if (isList && isType) {
        editor.setBlocks(types.para).unwrapBlock(types.bullets).unwrapBlock(types.numbers)
      } else if (isList) {
        editor.unwrapBlock(type === types.bullets ? types.numbers : types.bullets).wrapBlock(type)
      } else {
        editor.setBlocks(types.list_item).wrapBlock(type)
      }
    } else {
      // Handle everything else
      const isActive = this.has_block(type)
      const isList = this.has_block(types.list_item)

      if (isList) {
        editor.setBlocks(isActive ? types.para : type).unwrapBlock(types.bullets).unwrapBlock(types.numbers)
      } else {
        editor.setBlocks(isActive ? types.para : type)
      }
    }
  }

  ref = editor => {
    this.editor = editor
  }

  on_change = ({value}) => {
    this.setState({value})
    // console.log(JSON.stringify(value.toJSON(), null, 2))
    // console.log(Serializer.serialize(value))
  }

  render () {
    return (
      <div>
        <div className="d-flex justify-content-end mb-1">
          <ButtonGroup>
            <MarkButton main={this} type="bold" title="Bold Ctrl+B"/>
            <MarkButton main={this} type="italic" title="Italic Ctrl+I"/>
            <MarkButton main={this} type="underlined" title="Underline Ctrl+U" icon={fas.faUnderline}/>
            {/*<BlockButton main={this} type="bulleted-list" title="Bullet Points" icon={fas.fa}/>*/}
            <BlockButton main={this} type="bulleted-list" title="Bullet Points" icon={fas.faList}/>
            <BlockButton main={this} type="numbered-list" title="Numbered List" icon={fas.faListOl}/>
          </ButtonGroup>
        </div>
        <div className="editor">
          <Editor
            spellCheck
            placeholder={this.props.placeholder}
            disabled={this.props.disabled}
            value={this.state.value}
            ref={this.ref}
            onChange={this.on_change}
            onKeyDown={on_key_down}
            renderBlock={render_block}
            renderMark={render_mark}
          />
        </div>
      </div>
    )
  }
}


const _fa_name = s => 'fa' + s.charAt(0).toUpperCase() + s.slice(1)

const mark_active = (main, type) => main.state.value.activeMarks.some(mark => mark.type === type)

const MarkButton = ({main, type, title, icon = null}) => (
  <Button title={title} onMouseDown={e => main.toggle_mark(e, type)} active={mark_active(main, type)}
          disabled={main.props.disabled}>
    <FontAwesomeIcon icon={icon || fas[ _fa_name(type)]}/>
  </Button>
)

const BlockButton = ({main, type, title, icon = null}) => (
  <Button title={title} onMouseDown={e => main.toggle_block(e, type)} active={main.block_active(type)}
          disabled={main.props.disabled}>
    <FontAwesomeIcon icon={icon || fas[_fa_name(type)]}/>
  </Button>
)

const on_key_down = (e, editor, next) => {
  let mark

  if (e.key === ' ') {
    return on_space(e, editor, next)
  } else if (e.key === 'Backspace') {
    return on_backspace(e, editor, next)
  } else if (e.key === 'Enter') {
    return on_enter(e, editor, next)
  } else if (bold_key(e)) {
    mark = 'bold'
  } else if (italic_key(e)) {
    mark = 'italic'
  } else if (underline_key(e)) {
    mark = 'underlined'
  } else if (code_key(e)) {
    mark = 'code'
  } else {
    return next()
  }

  e.preventDefault()
  editor.toggleMark(mark)
}

const render_block = (props, editor, next) => {
  const {attributes, children, node} = props

  switch (node.type) {
    case types.para:
      return <p {...attributes}>{children}</p>
    case types.block_quote:
      return <blockquote {...attributes}>{children}</blockquote>
    case types.bullets:
      return <ul {...attributes}>{children}</ul>
    case types.numbers:
    case 'ordered-list':
      return <ol {...attributes}>{children}</ol>
    case 'todo-list':
      return <ul {...attributes}>{children}</ul>
    case 'table':
      return <table {...attributes}>{children}</table>
    case 'table-row':
      return <tr {...attributes}>{children}</tr>
    case 'table-head':
      return <th {...attributes}>{children}</th>
    case 'table-cell':
      return <td {...attributes}>{children}</td>
    case types.list_item:
      return <li {...attributes}>{children}</li>
    case 'horizontal-rule':
      return <hr />
    case 'code':
      return <code {...attributes}>{children}</code>
    case 'image':
      return <img src={props.src} title={props.title} alt={props.title} />
    case 'link':
      return <a href={props.href}>{children}</a>
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

const render_mark = (props, editor, next) => {
  const {children, mark, attributes} = props

  switch (mark.type) {
    case 'bold':
      return <strong {...attributes}>{children}</strong>
    case 'code':
      return <code {...attributes}>{children}</code>
    case 'italic':
      return <em {...attributes}>{children}</em>
    case 'underlined':
      return <u {...attributes}>{children}</u>
    case 'deleted':
      return <del {...attributes}>{children}</del>
    case 'added':
      return <mark {...attributes}>{children}</mark>
    default:
      return next()
  }
}

const on_enter = (e, editor, next) => {
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

  if (!/(heading\d|block-quote)/.test(startBlock.type)) {
    return next()
  }

  e.preventDefault()
  editor.splitBlock().setBlocks(types.para)
}

const on_backspace = (e, editor, next) => {
  const {value} = editor
  const {selection} = value
  if (selection.isExpanded) {
    return next()
  }
  if (selection.start.offset !== 0) {
    return next()
  }

  const {startBlock} = value
  if (startBlock.type === types.para) {
    return next()
  }

  e.preventDefault()

  console.log('type', startBlock.type)
  if (startBlock.type === types.list_item) {
    editor.setBlocks(types.para).unwrapBlock(types.bullets).unwrapBlock(types.numbers)
  }
}

const on_space = (e, editor, next) => {
  const {value} = editor
  const {selection} = value
  if (selection.isExpanded) {
    return next()
  }

  const {startBlock} = value
  const {start} = selection
  const chars = startBlock.text.slice(0, start.offset).replace(/\s*/g, '')
  let type
  if (['*', '-', '+'].includes(chars)) {
    if (startBlock.type === types.list_item) {
      return next()
    }
    type = types.list_item
  } else if ('>' === chars) {
    type = types.block_quote
  } else if (/^#{1,6}$/.test(chars)) {
    type = `heading${chars.length}`
  } else {
    return next()
  }
  e.preventDefault()

  editor.setBlocks(type)

  if (type === types.list_item) {
    editor.wrapBlock(types.bullets)
  }

  editor.moveFocusToStartOfNode(startBlock).delete()
}
