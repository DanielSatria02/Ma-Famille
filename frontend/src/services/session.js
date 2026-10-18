// Manager session token, kept in localStorage so a reload stays logged in.
const TOKEN_KEY = 'ma-famille.manager-token'
// The contact a client booked with: proves ownership of their bookings.
const CONTACT_KEY = 'ma-famille.customer-contact'
// A signed-in customer's session. Separate from the contact above on purpose:
// the contact is whatever was typed, this is what the server vouched for.
const CUSTOMER_TOKEN_KEY = 'ma-famille.customer-token'

function read(key) {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    // Private mode / storage disabled: everything falls back to the open dev mode.
    return ''
  }
}

function write(key, value) {
  try {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

export function getManagerToken() {
  return read(TOKEN_KEY)
}

export function setManagerToken(token) {
  write(TOKEN_KEY, token)
}

export function clearManagerToken() {
  setManagerToken('')
}

export function getCustomerContact() {
  return read(CONTACT_KEY)
}

export function setCustomerContact(contact) {
  write(CONTACT_KEY, contact)
}

export function getCustomerToken() {
  return read(CUSTOMER_TOKEN_KEY)
}

export function setCustomerToken(token) {
  write(CUSTOMER_TOKEN_KEY, token)
}

export function clearCustomerToken() {
  setCustomerToken('')
}
