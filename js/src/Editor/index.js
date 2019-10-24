import React from 'react'
import MarkdownSerializer from '@edithq/slate-md-serializer'
import {Value} from 'slate'
import {Editor as SlateEditor} from 'slate-react'
import {isKeyHotkey} from 'is-hotkey'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {
  Button,
  ButtonGroup,
  FormGroup,
  FormFeedback,
  Tooltip,
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
  word_selection,
  Drag,
} from './utils'
import {EditLink, as_url} from './EditLink'

const Serializer = new MarkdownSerializer()

const bold_key = isKeyHotkey('mod+b')
const italic_key = isKeyHotkey('mod+i')
const underline_key = isKeyHotkey('mod+u')
const quote_key = isKeyHotkey('mod+q')
const code_key = isKeyHotkey('mod+`')
const link_key = isKeyHotkey('mod+k')

export const empty_editor = {
  slate_value: Value.fromJSON(raw_empty),
  markdown: '',
  has_changed: false,
}
export const from_markdown = markdown => (
  {
    slate_value: null,
    markdown,
    has_changed: false,
  }
)

const ls_key = 'raw_editor_mode'

const help_args = {
  href: 'https://guides.github.com/features/mastering-markdown/',
  target: '_blank',
  rel: 'noopener noreferrer',
}

export class Editor extends React.Component {
  constructor (props) {
    super(props)
    this.state = {link: null, raw_mode: !!localStorage[ls_key]}
  }

  componentDidMount () {
    this._initial_value = this.props.content.markdown
  }

  asyncSetState = s => (
    new Promise(resolve => this.setState(s, () => resolve()))
  )

  has_block = type => this.props.content.slate_value && this.slate_value().blocks.some(node => node.type === type)

  block_active = type => {
    if (!this.props.content.slate_value) {
      return false
    }
    const {document, blocks} = this.props.content.slate_value
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

  create_link = e => {
    e.preventDefault()
    const text = word_selection(this.editor)
    const url = as_url(text)
    if (url) {
      setTimeout(() => this.set_link(text, url), 0)
    } else {
      this.link_modal()
    }
  }

  link_modal = () => {
    let link = word_selection(this.editor)
    const link_node = this.slate_value().inlines.find(i => i.type === T.link)
    if (link_node && link_node.text.includes(link)) {
      link = {href: link_node.data.get('href'), title: link_node.text}
    }
    setTimeout(() => this.setState({link}), 0)
  }

  remove_link = e => {
    e.preventDefault()
    this.editor.unwrapInline(T.link)
  }

  set_link = async (title, href) => {
    // have to make sure the previous render is complete before mutating the editor
    await this.asyncSetState({link: null})

    const link_node = this.slate_value().inlines.find(i => i.type === T.link)
    if (link_node && link_node.text.includes(this.editor.value.fragment.text)) {
      this.editor.moveToRangeOfNode(link_node)
    }

    if (this.editor.value.selection.isExpanded) {
      this.editor.delete()
    }
    this.editor
      .insertText(title)
      .moveFocusBackward(title.length)
      .wrapInline({type: T.link, data: {href}})
      .moveToEnd()
  }

  toggle_mode = e => {
    e.preventDefault()
    this.setState(s => {
      const raw_mode = !s.raw_mode
      if (raw_mode) {
        localStorage[ls_key] = '1'
      } else {
        localStorage.removeItem(ls_key)
      }
      return {raw_mode}
    })
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

  onKeyDown = (e, editor, next) => {
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
    } else if (link_key(e)) {
      return this.create_link(e)
    } else {
      return next()
    }

    e.preventDefault()
    editor.toggleMark(mark)
  }

  ref = editor => {
    this.editor = editor
  }

  onSlateChange = ({value}) => {
    // console.log(to_markdown(value))
    // console.log(JSON.stringify(value.toJSON(), null, 2))
    const markdown = Serializer.serialize(value)
    this.props.onChange({
      slate_value: value,
      markdown,
      has_changed: markdown !== this._initial_value,
    })
  }

  onTextareaChange = e => {
    const markdown = e.target.value
    this.props.onChange({
      slate_value: null,
      markdown,
      has_changed: markdown !== this._initial_value,
    })
  }

  slate_value = () => this.props.content.slate_value || Serializer.deserialize(this.props.content.markdown)

  onPaste = (e, editor) => {
    const raw = e.clipboardData.getData('Text')
    editor.insertText(raw)
  }

  render () {
    const value = this.props.content.slate_value
    let tooltip
    if (!this.state.link && value) {
      const link_node = value.inlines.find(i => i.type === T.link)
      if (link_node) {
        tooltip = {key: link_node.key, href: link_node.data.get('href')}
      }
    }

    const classes = combine_classes('md editor',  this.props.disabled && ' disabled', this.props.error && 'error')
    return (
      <div>
        <div className="d-flex justify-content-end mb-1">
          <ButtonGroup>
            <MarkButton main={this} type={T.link} title="Create Link Ctrl+k" onMouseDown={this.create_link}/>
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
            <Button title="Toggle raw markdown mode" color="light-border" type="button" tabIndex="-1"
                    onMouseDown={this.toggle_mode}>
              <FontAwesomeIcon icon={this.state.raw_mode ? fas.faToggleOn : fas.faToggleOff}/>
            </Button>
          </ButtonGroup>
        </div>
        {this.state.raw_mode ? (
          <div>
            <textarea
              autoFocus
              className={classes}
              placeholder={this.props.placeholder}
              value={this.props.content.markdown}
              onChange={this.onTextareaChange}
              disabled={this.props.disabled}
            />
            <small className="text-muted">Your editor is in raw <a {...help_args}>markdown</a> mode.</small>
          </div>
        ) : (
          <div className={classes}>
            <SlateEditor
              spellCheck
              autoFocus
              id="slate-editor"
              placeholder={(value && value.focusBlock && value.focusBlock.type) === T.para ? this.props.placeholder: ''}
              readOnly={this.props.disabled}
              value={this.slate_value()}
              ref={this.ref}
              onKeyDown={this.onKeyDown}
              onChange={this.onSlateChange}
              onPaste={this.onPaste}
              renderBlock={render_block}
              renderInline={render_inline}
              renderMark={render_mark}
            />
            <Drag editor_id="slate-editor"/>
          </div>
        )}
        <EditLink
          link={this.state.link}
          close={() => this.setState({link: null})}
          finished={this.set_link}
        />
        {tooltip && (
          <Tooltip isOpen={true} placement="top" target={'link-' + tooltip.key}>
            <div className="text-center">
              {tooltip.href}
            </div>
            <div className="d-flex justify-content-around">
              <button className="link-button" onClick={() => this.link_modal()}>change</button>
              <button className="link-button" onClick={this.remove_link}>remove</button>
            </div>
          </Tooltip>
        )}
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
        <SlateEditor
          readOnly={true}
          value={Serializer.deserialize(this.props.value)}
          renderBlock={render_block}
          renderInline={render_inline}
          renderMark={render_mark}
        />
      </div>
    )
  }
}

export const EditorInput = ({className, field, disabled, error, value, onChange}) => (
  <FormGroup className={className || field.className}>
    <InputLabel field={field}/>
    <Editor content={value || empty_editor} disabled={disabled} onChange={onChange} error={error}/>
    <FormFeedback className={error ? 'd-block': ''}>{error}</FormFeedback>
    <InputHelpText field={field}/>
  </FormGroup>
)
