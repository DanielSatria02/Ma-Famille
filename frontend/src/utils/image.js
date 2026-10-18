import { API_ORIGIN } from '../services/api.js'

// `image_url` is either a link the manager pasted or an upload path under /media.
// Only the second one needs the API origin in front of it.
export function resolveImage(value) {
  const url = String(value ?? '').trim()
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('/')) return `${API_ORIGIN}${url}`
  return ''
}

export function initialOf(name) {
  return String(name ?? '?').trim().charAt(0).toUpperCase() || '?'
}
