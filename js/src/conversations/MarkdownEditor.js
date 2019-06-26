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

const isBoldHotkey = isKeyHotkey('mod+b')
const isItalicHotkey = isKeyHotkey('mod+i')
const isUnderlinedHotkey = isKeyHotkey('mod+u')
const isCodeHotkey = isKeyHotkey('mod+`')


const DEFAULT_NODE = 'paragraph'

export default class MarkdownEditor extends React.Component {
  state = {
    value: Serializer.deserialize(''), // TODO
  }

  has_block = type => {
    const {value} = this.state
    return value.blocks.some(node => node.type === type)
  }

  block_active = type => {
    let is_active = this.has_block(type)

    if (['numbered-list', 'bulleted-list'].includes(type)) {
      const {value: {document, blocks}} = this.state

      if (blocks.size > 0) {
        const parent = document.getParent(blocks.first().key)
        is_active = this.has_block('list-item') && parent && parent.type === type
      }
    }
    return is_active
  }

  on_click_mark = (e, type) => {
    e.preventDefault()
    this.editor.toggleMark(type)
  }

  on_click_block = (e, type) => {
    e.preventDefault()
    const {editor} = this
    const {value} = editor
    const {document} = value

    // Handle everything but list buttons.
    if (type !== 'bulleted-list' && type !== 'numbered-list') {
      const isActive = this.has_block(type)
      const isList = this.has_block('list-item')

      if (isList) {
        editor
          .setBlocks(isActive ? DEFAULT_NODE : type)
          .unwrapBlock('bulleted-list')
          .unwrapBlock('numbered-list')
      } else {
        editor.setBlocks(isActive ? DEFAULT_NODE : type)
      }
    } else {
      // Handle the extra wrapping required for list buttons.
      const isList = this.has_block('list-item')
      const isType = value.blocks.some(block => {
        return !!document.getClosest(block.key, parent => parent.type === type)
      })

      if (isList && isType) {
        editor
          .setBlocks(DEFAULT_NODE)
          .unwrapBlock('bulleted-list')
          .unwrapBlock('numbered-list')
      } else if (isList) {
        editor
          .unwrapBlock(
            type === 'bulleted-list' ? 'numbered-list' : 'bulleted-list'
          )
          .wrapBlock(type)
      } else {
        editor.setBlocks('list-item').wrapBlock(type)
      }
    }
  }

  ref = editor => {
    this.editor = editor
  }

  onChange = ({value}) => {
    this.setState({value})
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
            <BlockButton main={this} type="bulleted-list" title="Bullet Points" icon={fas.faList}/>
          </ButtonGroup>
        </div>
        <div className="editor">
          <Editor
            spellCheck
            placeholder={this.props.placeholder}
            disabled={this.props.disabled}
            value={this.state.value}
            ref={this.ref}
            onChange={this.onChange}
            onKeyDown={onKeyDown}
            renderBlock={renderBlock}
            renderMark={renderMark}
          />
        </div>
      </div>
    )
  }
}


const _fa_name = s => 'fa' + s.charAt(0).toUpperCase() + s.slice(1)

const mark_active = (main, type) => main.state.value.activeMarks.some(mark => mark.type === type)

const MarkButton = ({main, type, title, icon = null}) => (
  <Button title={title} onMouseDown={e => main.on_click_mark(e, type)} active={mark_active(main, type)}
          disabled={main.props.disabled}>
    <FontAwesomeIcon icon={icon || fas[ _fa_name(type)]}/>
  </Button>
)

const BlockButton = ({main, type, title, icon = null}) => (
  <Button title={title} onMouseDown={e => main.on_click_block(e, type)} active={main.block_active(type)}
          disabled={main.props.disabled}>
    <FontAwesomeIcon icon={icon || fas[_fa_name(type)]}/>
  </Button>
)

const onKeyDown = (e, editor, next) => {
  let mark

  if (isBoldHotkey(e)) {
    mark = 'bold'
  } else if (isItalicHotkey(e)) {
    mark = 'italic'
  } else if (isUnderlinedHotkey(e)) {
    mark = 'underlined'
  } else if (isCodeHotkey(e)) {
    mark = 'code'
  } else {
    return next()
  }

  e.preventDefault()
  editor.toggleMark(mark)
}

const renderBlock = (props, editor, next) => {
  const {attributes, children, node} = props

  switch (node.type) {
    case 'paragraph':
      return <p {...attributes}>{children}</p>
    case 'block-quote':
      return <blockquote {...attributes}>{children}</blockquote>
    case 'bulleted-list':
      return <ul {...attributes}>{children}</ul>
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
    case 'list-item':
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

const renderMark = (props, editor, next) => {
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
