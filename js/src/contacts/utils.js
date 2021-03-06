import React from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'

const _status = (className, text, icon) => (
  <span className={className}>{text} <FontAwesomeIcon icon={icon}/></span>
)

export const StatusDisplay = ({profile_status}) => {
  if (profile_status === 'active') {
    return _status('text-info', 'Active', fas.faComment)
  } else if (profile_status === 'away') {
    return _status('text-secondary', 'Away', fas.faPlaneDeparture)
  } else if (profile_status === 'dormant') {
    return _status('text-danger', 'Dormant', fas.faMinusCircle)
  } else {
    return null
  }
}

const dft_icons = {
  work: fas.faUserTie,
  organisation: fas.faBuilding,
}

export const ContactImage = ({c, large}) => {
  const image_url = c.image_url || c.c_image_url || c.p_image_url
  const img_size = large ? 150 : 40
  return (
    <div className={`contact-image${image_url ? '' : ' dft'} ${large ? 'large' : 'small'}`}>
      {image_url ? (
        <img src={image_url} width={img_size} height={img_size} alt={contact_name(c)}/>
      ) : (
        <FontAwesomeIcon icon={dft_icons[c.profile_type || c.c_profile_type || c.p_profile_type] || fas.faUser}/>
      )}
    </div>
  )
}

export const contact_name = c => {
  if (c.main_name) {
    return `${c.main_name} ${c.last_name || ''}`.trim()
  } else if (c.c_main_name) {
    return `${c.c_main_name} ${c.c_last_name || ''}`.trim()
  } else if (c.p_main_name) {
    return `${c.p_main_name} ${c.p_last_name || ''}`.trim()
  } else {
    return c.email
  }
}

export const form_fields = d => {
  const fields = {
    email: {max_length: 255, type: 'email', required: true},
    profile_type: {type: 'select', choices: ['personal', 'work', 'organisation'], default: 'personal'},
    main_name: {title: 'First Name', max_length: 63},
    last_name: {max_length: 63},
    strap_line: {max_length: 127},
    details: {type: 'rich_text'},
    image: {type: 'image', extra: {request_file_upload: window.logic.contacts.request_image_upload}},
  }

  if (d.profile_type === 'organisation') {
    fields.main_name = {title: 'Name', max_length: 63}
    delete fields.last_action
  }
  return fields
}
