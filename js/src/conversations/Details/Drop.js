import React from 'react'
import {Progress} from 'reactstrap'
import Dropzone from 'react-dropzone'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import file_icon from './file_icons'

const file_key = f => `${f.name}-${f.size}-${f.lastModified}`
const is_file_drag = e => e.dataTransfer.types.length === 1 && e.dataTransfer.types[0] === 'Files'
const failed_icon = fas.faMinusCircle


const FileSummary = ({preview, preview_icon, progress, filename, size, icon, message, file_key, remove_file}) => {
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
          {preview ? (
            <img src={preview} alt={filename} className="rounded"/>
          ) : (
            <FontAwesomeIcon icon={preview_icon} size="3x"/>
          )}
        </div>
        {filename}
        <div>
          {progress ? (
            <Progress value={progress} className="mt-1"/>
          ): (
            message ? (
              <span>{icon && <FontAwesomeIcon icon={icon}/>} {message}</span>
            ) : (
              <div className="font-weight-bold">{size}</div>
            )
          )}
        </div>
        <div>
        </div>
      </div>
      <div className={`preview-overlay ${over ? 'd-flex' : 'd-none'}`} onClick={() => remove_file(file_key)}>
        <FontAwesomeIcon icon={fas.faTimes} size="3x"/>
      </div>
    </div>
  )
}


const kb = 1024
const mb = kb ** 2
const gb = kb ** 3
const round_to = (s, dp) => dp === 0 ? Math.round(s) : Math.round(s * dp ** 2) / dp ** 2

function file_size (s) {
  if (s < kb) {
    return `${s}B`
  } else if (s < mb) {
    return `${round_to(s / kb, 0)}KB`
  } else if (s < gb) {
    return `${round_to(s / mb, 2)}MB`
  } else {
    return `${round_to(s / gb, 3)}GB`
  }
}

export default class Drop extends React.Component {
  constructor (props) {
    super(props)
    this.state = {}
    this.uploads = {}
    this.drop_ref = React.createRef()
  }

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

  update_file_state = (k, changes) => {
    this.setState({[k]: Object.assign({}, this.state[k], changes)})
  }

  show_error = (key, reason) => {
    this.update_file_state(key, {progress: null, icon: failed_icon, message: reason || 'A problem occurred'})
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
        this.update_file_state(key, {progress: null, icon: fas.faCheck})
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
        this.update_file_state(key, {progress: e.loaded / e.total * 100})
      }
    }
    xhr.send(form_data)
    this.uploads[key] = xhr
  }

  onDrop = (accepted_files, refused_files) => {
    const extra_state = {already_uploaded: false, dragging: false}
    for (let file of accepted_files) {
      const key = file_key(file)
      if (this.state[key]) {
        extra_state.already_uploaded = true
      } else {
        console.log(file)
        extra_state[key] = {filename: file.name, size: file_size(file.size), file_key: key, progress: 1}
        if (file.type.startsWith('image/')) {
          extra_state[key].preview = URL.createObjectURL(file)
        } else {
          extra_state[key].preview_icon = file_icon(file.type)
        }
        this.upload_file(key, file)
      }
    }
    for (let file of refused_files) {
      extra_state[file_key(file)] = {
        filename: file.name,
        preview: URL.createObjectURL(file),
        icon: failed_icon,
        message: 'Not a valid file',
      }
    }
    this.setState(extra_state)
  }

  onClickAttach = e => {
    e.preventDefault()
    this.drop_ref.current && this.drop_ref.current.open()
  }

  remove_file = key => {
    this.setState(Object.assign({}, this.state, {[key]: null, already_uploaded: false}))
    this.uploads[key].abort()
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
              <input {...getInputProps()} />
              <span className="text-muted">
                Drop files here, or click <a href="." onClick={this.onClickAttach}>here</a> to select a file to attach.
              </span>
              <div className="previews">
                {Object.values(this.state).filter(item => item && item.filename).map((item, i) => (
                  <FileSummary key={i} {...item} remove_file={this.remove_file}/>
                ))}
              </div>
              <div className={`full-overlay ${this.state.dragging ? 'd-flex': 'd-none'}`}>
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
