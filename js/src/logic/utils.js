export const unix_ms = s => (new Date(s)).getTime()

export const per_page = 50  // list pagination

export function offset_limit (arr, page) {
  const offset = (page - 1) * per_page
  return arr.slice(offset, offset + per_page)
}

export const bool_int = bool => bool ? 1: 0
