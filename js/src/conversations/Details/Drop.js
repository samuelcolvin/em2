import React from 'react'
import {Progress} from 'reactstrap'
import Dropzone from 'react-dropzone'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {file_icon, file_size} from './files'

const file_key = f => `${f.name}-${f.size}-${f.lastModified}`
const is_file_drag = e => e.dataTransfer.types.length === 1 && e.dataTransfer.types[0] === 'Files'
const failed_icon = fas.faMinusCircle


const FileSummary = props => {
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
        {props.filename}
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
           onClick={() => props.remove_file(file_key)}>
        <FontAwesomeIcon icon={fas.faTimes} size="3x"/>
      </div>
    </div>
  )
}

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
    const data = await window.logic.conversations.request_file_upload(this.props.conv, file.name, file.type, file.size)

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

  set_files = () => (
    this.props.set_files(Object.values(this.state).filter(i => i && i.content_id).map(i => i.content_id))
  )

  onDrop = (accepted_files, refused_files) => {
    if (this.props.locked) {
      return
    }
    this.setState({already_uploaded: false, dragging: false})
    for (let file of accepted_files) {
      const key = file_key(file)
      if (this.state[key]) {
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
    if (refused_files.length) {
      throw Error('refused files not supported')
    }
  }

  onClickAttach = e => {
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
    return (
      <div>
        <Dropzone ref={this.drop_ref}
                  onDrop={this.onDrop}
                  noClick={true}
                  maxSize={1024**3}
                  onDragStart={e => console.log('onDragStart', e)}>
          {({getRootProps, getInputProps}) => (
            <div className="dropzone mb-1" {...getRootProps()}>
              {this.props.children}
              <input {...getInputProps()}/>
              <span className="text-muted">
                Drag and drop files, or click <a href="." onClick={this.onClickAttach}>here</a>
                &nbsp;to select a file to attach.
              </span>
              <div className="previews">
                {this.props.files.map((file, i) => (
                  <FileSummary key={i} {...file} locked={this.props.locked} remove_file={this.remove_file}/>
                ))}
              </div>
              <div className={`full-overlay ${!this.props.locked && this.state.dragging ? 'd-flex': 'd-none'}`}>
                <div className="h1">
                  Drop files here
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
