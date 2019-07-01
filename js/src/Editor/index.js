import React from 'react'
import MarkdownSerializer from '@edithq/slate-md-serializer'
import {Value} from 'slate'
import {Editor as RawEditor} from 'slate-react'
import {isKeyHotkey} from 'is-hotkey'
import {isEqual} from 'lodash'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {
  ButtonGroup,
  FormGroup,
  FormFeedback,
} from 'reactstrap'
import {InputLabel, InputHelpText, combine_classes} from 'reactstrap-toolbox'
import {
  T,
  is_list_type,
  raw_empty,
  MarkButton,
  BlockButton,
  render_block,
  render_inline,
  render_mark,
  on_enter,
  on_backspace,
  on_space,
  apply_code_block,
} from './utils'
import EditLink from './EditLink'

const Serializer = new MarkdownSerializer()

const bold_key = isKeyHotkey('mod+b')
const italic_key = isKeyHotkey('mod+i')
const underline_key = isKeyHotkey('mod+u')
const quote_key = isKeyHotkey('mod+q')
const code_key = isKeyHotkey('mod+`')

export const empty_editor = () => Value.fromJSON(raw_empty)
export const has_content = v => !isEqual(v.toJSON(), raw_empty)
export const to_markdown = v => Serializer.serialize(v)
const from_markdown = v => Serializer.deserialize(v)

export class Editor extends React.Component {
  state = {edit_link: null}

  has_block = type => this.props.value.blocks.some(node => node.type === type)

  block_active = type => {
    const {document, blocks} = this.props.value
    if (is_list_type(type)) {
      if (blocks.size > 0) {
        const parent = document.getParent(blocks.first().key)
        return this.has_block(T.list_item) && parent && parent.type === type
      }
    } else if (type === T.heading) {
      return blocks.some(node => node.type.startsWith(T.heading))
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
        apply_code_block(editor)
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

  set_link = e => {
    e.preventDefault()
    console.log('set_link')
    this.setState({edit_link: 'https://foobar.com'})
  }

  disable_button = (type, mode) => {
    if (this.props.disabled) {
      return true
    } else if (type === T.code && mode === 'block') {
      return false
    } else {
      return this.has_block(T.code_line)
    }
  }

  on_key_down = (e, editor, next) => {
    if (e.key === ' ') {
      return on_space(e, editor, next)
    } else if (e.key === 'Backspace') {
      return on_backspace(e, editor, next)
    } else if (e.key === 'Enter') {
      return on_enter(e, editor, next)
    } else if (this.has_block(T.code_line)) {
      return next()
    }

    let mark
    if (bold_key(e)) {
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
    // console.log(to_markdown(value))
    this.props.onChange(value)
  }

  render () {
    const {startBlock} = this.props.value
    return (
      <div>
        <div className="d-flex justify-content-end mb-1">
          <ButtonGroup>
            <MarkButton main={this} type={T.link} title="Create Link" onMouseDown={this.set_link}/>
            <MarkButton main={this} type={T.bold} title="Bold Ctrl+b"/>
            <MarkButton main={this} type={T.italic} title="Italic Ctrl+i"/>
            <MarkButton main={this} type={T.underlined} title="Underline Ctrl+u" icon={fas.faUnderline}/>
            <MarkButton main={this} type={T.deleted} title="Strike Through" icon={fas.faStrikethrough}/>
            <MarkButton main={this} type={T.code} title="Inline Code Ctrl+`" icon={fas.faTerminal}/>
            <BlockButton main={this} type={T.code} title="Code Block"/>
            <BlockButton main={this} type={T.heading} title="Heading" onMouseDown={this.change_heading}/>
            <BlockButton main={this} type={T.block_quote} title="Quote Ctrl+q" icon={fas.faQuoteLeft}/>
            <BlockButton main={this} type={T.bullets} title="Bullet Points" icon={fas.faList}/>
            <BlockButton main={this} type={T.numbers} title="Numbered List" icon={fas.faListOl}/>
          </ButtonGroup>
        </div>
        <div className={combine_classes('md editor',  this.props.disabled && ' disabled', this.props.error && 'error')}>
          <RawEditor
            spellCheck
            placeholder={(startBlock && startBlock.type) === T.para ? this.props.placeholder: ''}
            readOnly={this.props.disabled}
            value={this.props.value}
            ref={this.ref}
            onChange={this.on_change}
            onKeyDown={this.on_key_down}
            renderBlock={render_block}
            renderMark={render_mark}
          />
        </div>
        <EditLink
          link={this.state.edit_link}
          update_link={edit_link => this.setState({edit_link})}
        />
      </div>
    )
  }
}

// TODO following local links, eg. to conversations, block links to settings, perhaps move this to an iframe
export class MarkdownRenderer extends React.Component {
  shouldComponentUpdate (nextProps) {
    return this.props.value !== nextProps.value
  }

  render () {
    return (
      <div className="md">
        <RawEditor
          readOnly={true}
          value={from_markdown(this.props.value)}
          renderBlock={render_block}
          renderMark={render_mark}
          renderInline={render_inline}
        />
      </div>
    )
  }
}

export const EditorInput = ({className, field, disabled, error, value, onChange}) => (
  <FormGroup className={className || field.className}>
    <InputLabel field={field}/>
    <Editor value={value || empty_editor()} disabled={disabled} onChange={onChange} error={error}/>
    <FormFeedback className={error ? 'd-block': ''}>{error}</FormFeedback>
    <InputHelpText field={field}/>
  </FormGroup>
)
