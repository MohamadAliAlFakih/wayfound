/**
 * Thin fetch wrapper for the Wayfound backend.
 * - Prefixes paths with /api (matches Vite proxy in vite.config.js).
 * - Attaches Authorization: Bearer <token> from localStorage when present.
 * - Sets Content-Type: application/json on requests with a body.
 * - Throws an Error with .status and .body on non-2xx responses.
 *
 * Usage: await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({...}) })
 */
export const TOKEN_STORAGE_KEY = 'wayfound_token'

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const headers = { ...(options.headers || {}) }
  if (options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const url = path.startsWith('/api') ? path : `/api${path}`
  const res = await fetch(url, { ...options, headers })
  const text = await res.text()
  let body
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!res.ok) {
    const detail = body && body.detail
    let message
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
    } else {
      message = `Request failed with status ${res.status}`
    }
    const err = new Error(message)
    err.status = res.status
    err.body = body
    throw err
  }
  return body
}
