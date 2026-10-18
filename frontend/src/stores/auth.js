import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { errorDetail, errorStatus, loginManager } from '../services/api.js'
import { clearManagerToken, getManagerToken, setManagerToken } from '../services/session.js'

// Manager session. `openAccess` covers local dev: with no MANAGER_PASSWORD set
// the backend answers 501 to /auth/login and the manager routes stay open, so
// the dashboard must not be locked behind a login that cannot succeed.
export const useAuthStore = defineStore('auth', () => {
  const token = ref(getManagerToken())
  const openAccess = ref(false)
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
      openAccess.value = false
      return true
    } catch (err) {
      if (errorStatus(err) === 501) {
        openAccess.value = true
        error.value = 'This server has no manager password set, so the dashboard stays open.'
        return true
      }
      error.value = errorStatus(err) === 401 ? 'Wrong password.' : errorDetail(err, 'Login failed.')
      return false
    } finally {
      loading.value = false
    }
  }

  function logout() {
    clearManagerToken()
    token.value = ''
    openAccess.value = false
    error.value = ''
  }

  return { token, openAccess, error, loading, isLoggedIn, login, logout }
})
