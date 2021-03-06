import * as fas from '@fortawesome/free-solid-svg-icons'

const main_types = {
  'image/': fas.faFileImage,
  'video/': fas.faFileVideo,
  'audio/': fas.faFileAudio,
}


const full_types = {
  'application/epub+zip': fas.faFileArchive,
  'application/java-archive': fas.faFileCode,
  'application/javascript': fas.faFileCode,
  'application/json': fas.faFileCode,
  'application/ld+json': fas.faFileCode,
  'application/msword': fas.faFileWord,
  'application/ogg': fas.faFileAudio,
  'application/pdf': fas.faFilePdf,
  'application/rtf': fas.faFileAlt,
  'application/sql': fas.faFileCode,
  'application/vnd.ms-excel': fas.faFileExcel,
  'application/vnd.ms-excel.sheet.macroEnabled.12': fas.faFileExcel,
  'application/vnd.ms-excel.template.macroEnabled.12': fas.faFileExcel,
  'application/vnd.ms-powerpoint': fas.faFilePowerpoint,
  'application/vnd.oasis.opendocument.presentation': fas.faFilePowerpoint,
  'application/vnd.oasis.opendocument.spreadsheet': fas.faFileExcel,
  'application/vnd.oasis.opendocument.text': fas.faFileWord,
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': fas.faFilePowerpoint,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': fas.faFileExcel,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': fas.faFileWord,
  'application/x-7z-compressed': fas.faFileArchive,
  'application/x-bzip': fas.faFileArchive,
  'application/x-bzip2': fas.faFileArchive,
  'application/x-python-code': fas.faFileCode,
  'application/x-python': fas.faFileCode,
  'application/x-rar-compressed': fas.faFileArchive,
  'application/x-sh': fas.faFileCode,
  'application/x-tar': fas.faFileArchive,
  'application/xhtml+xml': fas.faFileCode,
  'application/xml': fas.faFileCode,
  'application/zip': fas.faFileArchive,
  'text/calendar': fas.faFileMedical,
  'text/css': fas.faFileCode,
  'text/csv': fas.faFileCsv,
  'text/html': fas.faFileCode,
  'text/javascript': fas.faFileCode,
  'text/plain': fas.faFileAlt,
}

export function file_icon (content_type) {
  const ct = content_type.toLowerCase()
  return main_types[ct.match(/.*\//)[0]] || full_types[ct.trim()] || fas.faFile
}



const kb = 1024
const mb = kb ** 2
const gb = kb ** 3
const round_to = (s, dp) => dp === 0 ? Math.round(s) : Math.round(s * dp ** 2) / dp ** 2

export function file_size (size) {
  if (size < kb) {
    return `${size}B`
  } else if (size < mb) {
    return `${round_to(size / kb, 0)}KB`
  } else if (size < gb) {
    return `${round_to(size / mb, 2)}MB`
  } else {
    return `${round_to(size / gb, 3)}GB`
  }
}
