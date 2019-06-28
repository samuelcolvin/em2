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
const quote_key = isKeyHotkey('mod+q')
const code_key = isKeyHotkey('mod+`')

const T = {
  para: 'paragraph',
  bold: 'bold',
  italic: 'italic',
  underlined: 'underlined',
  code: 'code',
  code_line: 'code-line',
  bullets: 'bulleted-list',
  numbers: 'numbered-list',
  list_item: 'list-item',
  block_quote: 'block-quote',
}
const is_list_type = t => t === T.numbers || t=== T.bullets

export default class MessageEditor extends React.Component {
  state = {
    value: Serializer.deserialize(''), // TODO
  }

  has_block = type => this.state.value.blocks.some(node => node.type === type)

  block_active = type => {
    if (is_list_type(type)) {
      const {value: {document, blocks}} = this.state

      if (blocks.size > 0) {
        const parent = document.getParent(blocks.first().key)
        return this.has_block(T.list_item) && parent && parent.type === type
      }
    } else if (type === 'heading') {
      return this.state.value.blocks.some(node => node.type.startsWith('heading'))
    } else if (type === T.code) {
      return this.has_block(T.code_line)
    }
    return this.has_block(type)
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
      const is_list = this.has_block(T.list_item)
      const is_type = value.blocks.some(block => !!document.getClosest(block.key, parent => parent.type === type))

      if (is_list && is_type) {
        editor.setBlocks(T.para).unwrapBlock(T.bullets).unwrapBlock(T.numbers)
      } else if (is_list) {
        editor.unwrapBlock(type === T.bullets ? T.numbers : T.bullets).wrapBlock(type)
      } else {
        editor.setBlocks(T.list_item).wrapBlock(type)
      }
    } else if (type === T.code) {
      if (this.has_block(T.code_line)) {
        editor.setBlocks(T.para).unwrapBlock(type)
      } else {
        editor.setBlocks(T.code_line).wrapBlock(type)
      }
    } else {
      editor.setBlocks(this.has_block(type) ? T.para : type)
      if (this.has_block(T.list_item)) {
        editor.unwrapBlock(T.bullets).unwrapBlock(T.numbers)
      }
    }
  }

  change_heading = e => {
    e.preventDefault()
    const {type} = this.editor.value.startBlock
    let new_type = 'heading3'
    const h_match = type.match(/heading([1-3])/)
    if (h_match) {
      const level = parseInt(h_match[1])
      new_type = level === 1 ? T.para : `heading${level - 1}`
    }
    this.editor.setBlocks(new_type)
  }

  on_key_down = (e, editor, next) => {
    let mark

    if (e.key === ' ') {
      return on_space(e, editor, next)
    } else if (e.key === 'Backspace') {
      return on_backspace(e, editor, next)
    } else if (e.key === 'Enter') {
      return on_enter(e, editor, next)
    } else if (bold_key(e)) {
      mark = T.bold
    } else if (italic_key(e)) {
      mark = T.italic
    } else if (underline_key(e)) {
      mark = T.underlined
    } else if (quote_key(e)) {
      const type = T.block_quote
      return editor.setBlocks(this.has_block(type) ? T.para : type)
    } else if (code_key(e)) {
      mark = T.code
    } else {
      return next()
    }

    e.preventDefault()
    editor.toggleMark(mark)
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
    const {startBlock} = this.state.value
    return (
      <div>
        <div className="d-flex justify-content-end mb-1">
          <ButtonGroup>
            <MarkButton main={this} type={T.bold} title="Bold Ctrl+b"/>
            <MarkButton main={this} type={T.italic} title="Italic Ctrl+i"/>
            <MarkButton main={this} type={T.underlined} title="Underline Ctrl+u" icon={fas.faUnderline}/>
            <MarkButton main={this} type={T.code} title="Inline Code Ctrl+`" icon={fas.faTerminal}/>
            <BlockButton main={this} type={T.code} title="Code Block"/>
            <BlockButton main={this} type="heading" title="Heading" onMouseDown={this.change_heading}/>
            <BlockButton main={this} type={T.block_quote} title="Quote Ctrl+q" icon={fas.faQuoteLeft}/>
            <BlockButton main={this} type={T.bullets} title="Bullet Points" icon={fas.faList}/>
            <BlockButton main={this} type={T.numbers} title="Numbered List" icon={fas.faListOl}/>
          </ButtonGroup>
        </div>
        <div className="editor">
          <Editor
            spellCheck
            placeholder={(startBlock && startBlock.type) === T.para ? this.props.placeholder: ''}
            disabled={this.props.disabled}
            value={this.state.value}
            ref={this.ref}
            onChange={this.on_change}
            onKeyDown={this.on_key_down}
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

const BlockButton = ({main, type, title, onMouseDown = null, icon = null}) => (
  <Button title={title}
          onMouseDown={e => (onMouseDown || main.toggle_block)(e, type)}
          active={main.block_active(type)}
          disabled={main.props.disabled}>
    <FontAwesomeIcon icon={icon || fas[_fa_name(type)]}/>
  </Button>
)

const render_block = (props, editor, next) => {
  const {attributes, children, node} = props

  switch (node.type) {
    case T.para:
      return <p {...attributes}>{children}</p>
    case T.block_quote:
      return <blockquote {...attributes}>{children}</blockquote>
    case T.bullets:
      return <ul {...attributes}>{children}</ul>
    case T.numbers:
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
    case T.list_item:
      return <li {...attributes}>{children}</li>
    case 'horizontal-rule':
      return <hr />
    case T.code:
      return <pre><code {...attributes}>{children}</code></pre>
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
    case T.bold:
      return <strong {...attributes}>{children}</strong>
    case 'code':
      return <code {...attributes}>{children}</code>
    case T.italic:
      return <em {...attributes}>{children}</em>
    case T.underlined:
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

  if (/(heading\d|block-quote)/.test(startBlock.type)) {
    e.preventDefault()
    editor.splitBlock().setBlocks(T.para)
  } else {
    next()
  }
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

  const {type} = value.startBlock
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
    if (startBlock.type === T.list_item) {
      return next()
    }
    type = T.list_item
  } else if ('>' === chars) {
    type = T.block_quote
  } else if (/^#{1,6}$/.test(chars)) {
    type = `heading${chars.length}`
  } else if ('```' === chars) {
    type = T.code_line
  } else {
    return next()
  }
  e.preventDefault()

  editor.setBlocks(type)

  if (type === T.list_item) {
    editor.wrapBlock(T.bullets)
  } else if (type === T.code_line) {
    editor.wrapBlock(T.code)
  }

  editor.moveFocusToStartOfNode(startBlock).delete()
}
