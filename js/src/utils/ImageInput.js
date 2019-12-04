import React from 'react'
import {FormGroup, FormFeedback} from 'reactstrap'
import {InputHelpText} from 'reactstrap-toolbox'
import Drop, {FileSummary} from './Drop'

const Help = ({onClick}) => (
  <span className="text-muted">
    Drag an image here, or <a href="." onClick={onClick}>click</a> to select one.
  </span>
)

const image_content_types = (
  'image/png,image/jpeg,image/gif,image/svg+xml,image/tiff,image/bmp,' +
  'image/vnd.microsoft.icon,image/webp,image/x-icon,image/x‑xbm'
)

export default ({className, field, error, value, onChange, request_file_upload}) => (
  <FormGroup className={className || field.className}>
    <Drop
      help={Help}
      hover_msg="Drop image here"
      update_file={(key, update) => onChange({...(value || {}), ...update})}
      remove_file={() => onChange(null)}
      files={value ? [value] : []}
      request_file_upload={request_file_upload}
      add_file={f => onChange(f)}
      maxSize={10 * 1024 ** 2}
      acceptable_files={image_content_types}
    >
      <div className="image-preview">
        {value ? (
          <FileSummary {...(value || {})} remove_file={() => onChange(null)}/>
        ) : <div className="no-image"/>}
      </div>
      {error && <FormFeedback>{error}</FormFeedback>}
      <InputHelpText field={field}/>
    </Drop>
  </FormGroup>
)
