import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { errorDetail, errorStatus, loginManager } from '../services/api.js'
import { clearManagerToken, getManagerToken, setManagerToken } from '../services/session.js'

const OPEN_ACCESS_KEY = 'ma-famille.open-access'

// "15 minutes" / "45 seconds" — reads better than a raw number.
function waitSecondsLabel(seconds) {
  if (seconds < 60) return `${seconds} seconds`
  const minutes = Math.round(seconds / 60)
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}

function readOpenAccess() {
  try {
    return sessionStorage.getItem(OPEN_ACCESS_KEY) === '1'
  } catch {
    return false
  }
}

function writeOpenAccess(value) {
  try {
    if (value) sessionStorage.setItem(OPEN_ACCESS_KEY, '1')
    else sessionStorage.removeItem(OPEN_ACCESS_KEY)
  } catch {
    /* ignore */
  }
}

// Manager session. `openAccess` covers local dev: with no MANAGER_PASSWORD set
// the backend answers 501 to /auth/login and the manager routes stay open, so
// the dashboard must not be locked behind a login that cannot succeed.
export const useAuthStore = defineStore('auth', () => {
  const token = ref(getManagerToken())
  const openAccess = ref(readOpenAccess())
  const error = ref('')
  const loading = ref(false)

  const isLoggedIn = computed(() => Boolean(token.value) || openAccess.value)

  async function login({ email = '', password = '' }) {
    if (loading.value) return false
    loading.value = true
    error.value = ''
    try {
      const data = await loginManager({ email, password })
      setManagerToken(data.token)
      token.value = data.token
      writeOpenAccess(false)
      openAccess.value = false
      return true
    } catch (err) {
      if (errorStatus(err) === 501) {
        writeOpenAccess(true)
        openAccess.value = true
        error.value = 'This server has no manager password set, so the dashboard stays open.'
        return true
      }
      if (errorStatus(err) === 429) {
        // The lockout carries a Retry-After in seconds; say when to come back
        // instead of leaving the manager guessing.
        const seconds = Number(err?.response?.headers?.['retry-after'])
        const wait = Number.isFinite(seconds) && seconds > 0 ? seconds : 0
        error.value = wait
          ? `Too many attempts. Try again in ${waitSecondsLabel(wait)}.`
          : 'Too many attempts. Try again shortly.'
        return false
      }
      error.value = errorStatus(err) === 401 ? 'Wrong password.' : errorDetail(err, 'Login failed.')
      return false
    } finally {
      loading.value = false
    }
  }

  // Server first, then local: revoking puts the token on the backend deny-list
  // so it cannot be replayed for the rest of its 480-minute life. A failed call
  // (offline, 401 because it already expired) must never trap the manager in a
  // logged-in state — the local session is always dropped either way.
  async function logout() {
    const hadToken = Boolean(token.value)
    if (hadToken) {
      try {
        await logoutManager()
      } catch {
        /* the local clear below is what matters */
      }
    }
    clearManagerToken()
    writeOpenAccess(false)
    token.value = ''
    openAccess.value = false
    error.value = ''
  }

  return { token, openAccess, error, loading, isLoggedIn, login, logout }
})
