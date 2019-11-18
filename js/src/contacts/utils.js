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
