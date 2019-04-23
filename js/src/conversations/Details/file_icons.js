const main_types = {
  'image/': 'file-image',
  'video/': 'file-video',
  'audio/': 'file-audio',
}


const full_types = {
  'application/epub+zip': 'file-archive',
  'application/java-archive': 'file-code',
  'application/javascript': 'file-code',
  'application/json': 'file-code',
  'application/ld+json': 'file-code',
  'application/msword': 'file-word',
  'application/ogg': 'file-audio',
  'application/pdf': 'file-pdf',
  'application/rtf': 'file-alt',
  'application/sql': 'file-code',
  'application/vnd.ms-excel': 'file-excel',
  'application/vnd.ms-powerpoint': 'file-powerpoint',
  'application/vnd.oasis.opendocument.presentation': 'file-powerpoint',
  'application/vnd.oasis.opendocument.spreadsheet': 'file-excel',
  'application/vnd.oasis.opendocument.text': 'file-word',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'file-powerpoint',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'file-excel',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'file-word',
  'application/x-7z-compressed': 'file-archive',
  'application/x-bzip': 'file-archive',
  'application/x-bzip2': 'file-archive',
  'application/x-python-code': 'file-code',
  'application/x-python': 'file-code',
  'application/x-rar-compressed': 'file-archive',
  'application/x-sh': 'file-code',
  'application/x-tar': 'file-archive',
  'application/xhtml+xml': 'file-code',
  'application/xml': 'file-code',
  'application/zip': 'file-archive',
  'text/calendar': 'file-spreadsheet',
  'text/css': 'file-code',
  'text/csv': 'file-csv',
  'text/html': 'file-code',
  'text/javascript': 'file-code',
  'text/plain': 'file-alt',
}

export default function (content_type) {
  const ct = content_type.toLowerCase().trim()
  for (const [main_type, icon] of Object.entries(main_types)) {
    if (ct.startsWith(main_type)) {
      return icon
    }
  }
  return full_types[ct] || 'file'
}
