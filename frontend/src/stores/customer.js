import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  errorDetail,
  fetchMe,
  loginCustomer,
  logoutCustomer,
  registerCustomer,
} from '../services/api.js'
import {
  clearCustomerToken,
  getCustomerToken,
  setCustomerContact,
  setCustomerToken,
} from '../services/session.js'

// A signed-in customer. Before this existed a customer was only the contact
// typed into the booking form, so "My bookings" trusted whatever was entered.
//
// The token is restored from storage on start, then checked against the server
// once: a token can expire (14 days) or be revoked by a logout elsewhere, and
// finding that out at first paint is better than during a booking.
export const useCustomerStore = defineStore('customer', () => {
  const token = ref(getCustomerToken())
  const profile = ref(null)
  const loading = ref(false)
  const checked = ref(false)
  const error = ref('')

  const isSignedIn = computed(() => Boolean(token.value) && Boolean(profile.value))
  const displayName = computed(() => profile.value?.display_name ?? '')
  // The contact the account wants venues to reach, falling back to the email:
  // a booking still needs something to call, and email is always present.
  const contact = computed(() => profile.value?.phone || profile.value?.email || '')

  function adopt({ token: nextToken, customer }) {
    setCustomerToken(nextToken)
    token.value = nextToken
    profile.value = customer
    // Keep the booking form's contact in step with the account, so a
    // signed-in booking carries the contact the venue will actually reach.
    setCustomerContact(contact.value)
  }

  // Confirms a restored token still works. Never throws: an unreachable server
  // leaves the stored token alone rather than signing the customer out.
  async function restore() {
    if (!token.value) {
      checked.value = true
      return
    }
    try {
      profile.value = await fetchMe()
    } catch (err) {
      // 401 means it really is over; anything else (offline, 500) is not the
      // customer's doing, so keep the token and let a later call decide.
      if (err?.response?.status === 401) {
        clearCustomerToken()
        token.value = ''
        profile.value = null
      }
    } finally {
      checked.value = true
    }
  }

  async function login({ email, password }) {
    if (loading.value) return false
    loading.value = true
    error.value = ''
    try {
      adopt(await loginCustomer({ email, password }))
      return true
    } catch (err) {
      error.value =
        err?.response?.status === 401
          ? 'Wrong email or password.'
          : errorDetail(err, 'Could not sign you in.')
      return false
    } finally {
      loading.value = false
    }
  }

  async function register({ email, password, displayName, phone }) {
    if (loading.value) return false
    loading.value = true
    error.value = ''
    try {
      adopt(await registerCustomer({ email, password, displayName, phone }))
      return true
    } catch (err) {
      // 409 is "already registered" — point at signing in rather than retrying.
      error.value =
        err?.response?.status === 409
          ? 'That email is already registered. Sign in instead.'
          : errorDetail(err, 'Could not create the account.')
      return false
    } finally {
      loading.value = false
    }
  }

  // Server first, then local — same reasoning as the manager's logout: the
  // row behind the token has to go, or it keeps working for its full life.
  // A failed call must never trap the customer in a signed-in state.
  async function logout() {
    if (token.value) {
      try {
        await logoutCustomer()
      } catch {
        /* the local clear below is what matters */
      }
    }
    clearCustomerToken()
    token.value = ''
    profile.value = null
    error.value = ''
  }

  return {
    token,
    profile,
    loading,
    checked,
    error,
    isSignedIn,
    displayName,
    contact,
    restore,
    login,
    register,
    logout,
  }
})
