// Manager session token, kept in localStorage so a reload stays logged in.
const TOKEN_KEY = 'ma-famille.manager-token'

export function getManagerToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    // Private mode / storage disabled: everything falls back to the open dev mode.
    return ''
  }
}

export function setManagerToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

export function clearManagerToken() {
  setManagerToken('')
}
