import React from 'react'
import {FormGroup, FormFeedback} from 'reactstrap'
import {InputHelpText} from 'reactstrap-toolbox'
import * as fas from '@fortawesome/free-solid-svg-icons'
import Drop, {FileSummary} from './Drop'

const Help = ({onClick}) => (
  <span className="text-muted">
    Drag an image here, or <a href="." onClick={onClick}>click</a> to select one.
  </span>
)

const image_content_types = 'image/png,image/jpeg,image/gif,image/svg+xml,image/tiff,image/bmp,image/webp,image/x‑xbm'

export default ({className, field, error, value, onChange, request_file_upload, disabled}) => {
  let file = value || {}
  if (typeof value === 'string') {
    file = {
      done: true,
      file_key: value,
      filename: 'current image',
      icon: fas.faCheck,
      preview: value,
      size: '',
    }
  }
  return (
    <FormGroup className={className || field.className}>
      <Drop
        help={Help}
        locked={disabled}
        hover_msg="Drop image here"
        update_file={(key, update) => onChange({...file, ...update})}
        remove_file={() => onChange(null)}
        files={value ? [file] : []}
        request_file_upload={request_file_upload}
        add_file={f => onChange(f)}
        maxSize={10 * 1024 ** 2}
        acceptable_files={image_content_types}
      >
        <div className="image-preview">
          {value ? (
            <FileSummary {...file} remove_file={() => !disabled && onChange(null)} locked={disabled}/>
          ) : <div className="no-image"/>}
        </div>
        {error && <FormFeedback className="d-block">{error}</FormFeedback>}
        <InputHelpText field={field}/>
      </Drop>
    </FormGroup>
  )
}
