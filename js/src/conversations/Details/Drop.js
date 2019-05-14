import React from 'react'
import {Progress} from 'reactstrap'
import Dropzone from 'react-dropzone'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'

const file_key = f => `${f.name}-${f.size}-${f.lastModified}`

const failed_icon = fas.faMinusCircle


export default class Drop extends React.Component {
  constructor (props) {
    super(props)
    this.state = {}
    this.uploads = []
  }

  componentWillUnmount () {
    for (let xhr of this.uploads) {
      xhr.abort()
    }
  }

  update_file_state = (k, changes) => {
    this.setState({[k]: Object.assign({}, this.state[k], changes)})
  }

  show_error = (key, reason) => {
    this.update_file_state(key, {icon: failed_icon, message: reason || 'A problem occurred'})
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
      this.update_file_state(key, {progress: 100, icon: fas.faCheck})
        this.props.update && this.props.update()
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
    this.uploads.push(xhr)
  }

  onDrop = (accepted_files, refused_files) => {
    const extra_state = {already_uploaded: false}
    for (let file of accepted_files) {
      const k = file_key(file)
      if (Object.keys(this.state).includes(k)) {
        extra_state.already_uploaded = true
      } else {
        extra_state[k] = {filename: file.name, preview: URL.createObjectURL(file)}
        this.upload_file(k, file)
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

  render () {
    return (
      <div>
        <Dropzone onDrop={this.onDrop} maxSize={1024**3}>
          {({getRootProps, getInputProps}) => (
            <div>
              <div className="dropzone" {...getRootProps()}>
                <input {...getInputProps()} />
                <p>Drop images here, or click to select images to upload.</p>
                <div className="previews">
                  {Object.values(this.state).filter(item => item.filename).map((item, i) => (
                    <div key={i} className="file-preview">
                      <div>
                        <img src={item.preview} alt={item.filename} className="img-thumbnail"/>
                      </div>
                      <div>
                        {item.progress && <Progress value={item.progress} className="mt-1"/>}
                      </div>
                      {item.icon && <FontAwesomeIcon icon={item.icon} className="mt-1"/>}
                      {item.message && <div className="mt-1">{item.message}</div>}
                    </div>
                  ))}
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
