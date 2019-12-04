import React from 'react'
import {Progress} from 'reactstrap'
import Dropzone from 'react-dropzone'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {file_icon, file_size} from './files'

const is_file_drag = e => e.dataTransfer.types.length === 1 && e.dataTransfer.types[0] === 'Files'
const failed_icon = fas.faMinusCircle


export const FileSummary = props => {
  const [over, setOver] = React.useState(false)
  const ref = React.createRef()
  const set_over = e => setOver(e.type === 'mouseenter')
  React.useEffect(() => {
    const node = ref.current
    node.addEventListener('mouseenter', set_over)
    node.addEventListener('mouseleave', set_over)
    return () => {
      node.removeEventListener('mouseenter', set_over)
      node.removeEventListener('mouseleave', set_over)
    }
  })
  return (
    <div ref={ref} className="file-summary">
      <div className="file-summary-main">
        <div className="file-preview">
          {props.preview ? (
            <img src={props.preview} alt={props.filename} className="rounded"/>
          ) : (
            <FontAwesomeIcon icon={props.preview_icon} size="3x"/>
          )}
        </div>
        <span className="file-name">{props.filename}</span>
        <div>
          {props.progress ? (
            <Progress value={props.progress} className="mt-1"/>
          ): (
            props.message ? (
              <span>{props.icon && <FontAwesomeIcon icon={props.icon}/>} {props.message}</span>
            ) : (
              <div className="font-weight-bold">{props.size}</div>
            )
          )}
        </div>
        <div>
        </div>
      </div>
      <div className={`preview-overlay ${!props.locked && over ? 'd-flex' : 'd-none'}`}
           onClick={() => props.remove_file(props.file_key)}>
        <FontAwesomeIcon icon={fas.faTimes} size="3x"/>
      </div>
    </div>
  )
}

const DefaultHelpComponent = ({onClick}) => (
  <span className="text-muted">
    Drag and drop files, or click <a href="." onClick={onClick}>here</a> to select one.
  </span>
)

export default class Drop extends React.Component {
  state = {}
  uploads = {}
  drop_ref = React.createRef()

  componentDidMount () {
    document.addEventListener('dragenter', this.onWindowDragEnter)
    document.addEventListener('dragleave', this.onWindowDragLeave)
    document.addEventListener('drop', this.onWindowDrop)
  }

  componentWillUnmount () {
    document.removeEventListener('dragenter', this.onWindowDragEnter)
    document.removeEventListener('dragleave', this.onWindowDragLeave)
    document.removeEventListener('drop', this.onWindowDrop)
    for (let xhr of Object.values(this.uploads)) {
      xhr.abort()
    }
  }

  onWindowDragEnter = e => {
    if (is_file_drag(e)) {
      this.setState({dragging: true})
    }
  }

  onWindowDragLeave = e => {
    if (is_file_drag(e) && e.target.id === 'root' && e.relatedTarget === null) {
      this.setState({dragging: false})
    }
  }

  onWindowDrop = () => this.setState({dragging: false})

  show_error = (key, reason) => {
    this.props.update_file(key, {progress: null, icon: failed_icon, message: reason || 'A problem occurred'})
  }

  upload_file = async (key, file) => {
    const data = await this.props.request_file_upload(file.name, file.type, file.size)

    const form_data = new FormData()
    for (let [name, value] of Object.entries(data.fields)) {
      form_data.append(name, value)
    }
    form_data.append('file', file)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', data.url, true)
    xhr.onload = event => {
      if (xhr.status === 204) {
        this.props.update_file(key, {progress: null, icon: fas.faCheck, content_id: data.content_id, done: true})
      } else {
        // const response_data = error_response(xhr)
        console.warn('uploading file failed at end', xhr)
        this.show_error(key)
      }
    }
    xhr.onerror = e => {
      console.warn('uploading file failed at beginning', xhr, e)
      this.show_error(key)
    }
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) {
        this.props.update_file(key, {progress: e.loaded / e.total * 100})
      }
    }
    xhr.send(form_data)
    this.uploads[key] = xhr
  }

  get_key = file => `${file.name}-${file.size}-${file.lastModified}`

  onDrop = (accepted_files, refused_files) => {
    if (this.props.locked) {
      return
    }
    this.setState({already_uploaded: false, dragging: false})
    for (let file of accepted_files) {
      const key = this.get_key(file)
      if (this.props.files.find(f => f.key === key)) {
        this.setState({already_uploaded: true})
      } else {
        const f = {key, filename: file.name, size: file_size(file.size), file_key: key, progress: 1}
        if (file.type.startsWith('image/')) {
          f.preview = URL.createObjectURL(file)
        } else {
          f.preview_icon = file_icon(file.type)
        }
        this.props.add_file(f)
        this.upload_file(key, file)
      }
    }
    for (let file of refused_files) {
      const key = this.get_key(file)
      if (this.props.files.find(f => f.key === key)) {
        this.setState({already_uploaded: true})
      } else {
        this.props.add_file({
          key,
          filename: file.name,
          progress: null,
          icon: failed_icon,
          preview_icon: failed_icon,
          message: 'Invalid file'
        })
      }
    }
  }

  selectDialog = e => {
    e.preventDefault()
    if (!this.props.locked) {
      this.drop_ref.current && this.drop_ref.current.open()
    }
  }

  remove_file = key => {
    if (!this.props.locked) {
      this.props.remove_file(key)
      this.setState({already_uploaded: false})
      this.uploads[key].abort()
    }
  }

  render () {
    const HelpComponent = this.props.help || DefaultHelpComponent
    const SummaryComponent = this.props.summary
    return (
      <div>
        <Dropzone ref={this.drop_ref}
                  onDrop={this.onDrop}
                  noClick={true}
                  maxSize={this.props.maxSize}
                  accept={this.props.acceptable_files}>
          {({getRootProps, getInputProps}) => (
            <div className="dropzone mb-1" {...getRootProps()}>
              {this.props.children}
              <input {...getInputProps()}/>
              <span className="text-muted">
                <HelpComponent onClick={this.selectDialog}/>
              </span>
              {SummaryComponent && <SummaryComponent {...this.props} remove_file={this.remove_file}/>}
              <div className={`full-overlay ${!this.props.locked && this.state.dragging ? 'd-flex': 'd-none'}`}>
                <div className="h1">
                  {this.props.hover_msg || 'Drop files here'}
                </div>
              </div>
            </div>
          )}
        </Dropzone>
        {this.state.already_uploaded && (
          <small className="form-error mt-1">
            File already uploaded.
          </small>
        )}
      </div>
    )
  }
}
