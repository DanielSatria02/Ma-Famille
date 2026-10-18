import axios from 'axios'

import { getManagerToken } from './session.js'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 8000,
})

// Manager routes want `X-Manager-Token`; one interceptor covers every call.
api.interceptors.request.use((config) => {
  const token = getManagerToken()
  if (token) config.headers['X-Manager-Token'] = token
  return config
})

// The backend puts a human-readable reason in `detail`; surface it verbatim.
export function errorDetail(error, fallback = 'Something went wrong.') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (error?.response?.status === 401) return 'Please log in as manager first.'
  if (!error?.response) return 'The server is not reachable.'
  return fallback
}

export function errorStatus(error) {
  return error?.response?.status ?? 0
}

export async function fetchHealth() {
  const res = await api.get('/v1/health')
  return res.data
}

export async function fetchRoot() {
  const res = await api.get('/')
  return res.data
}

// --- Auth ---------------------------------------------------------------

export async function loginManager({ email, password }) {
  const res = await api.post('/v1/auth/login', { email: email || null, password })
  return res.data
}

// --- Venues, facilities, hours ------------------------------------------

export async function fetchVenues({ q, tag } = {}) {
  const res = await api.get('/v1/venues', { params: { q, tag } })
  return res.data
}

export async function fetchVenueTags() {
  const res = await api.get('/v1/venues/tags')
  return res.data
}

export async function fetchVenue(publicId) {
  const res = await api.get(`/v1/venues/${publicId}`)
  return res.data
}

export async function fetchVenueHours(publicId) {
  const res = await api.get(`/v1/venues/${publicId}/hours`)
  return res.data
}

export async function updateVenueHours(publicId, dayOfWeek, { opensAt, closesAt, isClosed = false }) {
  const res = await api.put(`/v1/venues/${publicId}/hours/${dayOfWeek}`, {
    opens_at: opensAt,
    closes_at: closesAt,
    is_closed: isClosed,
  })
  return res.data
}

export async function fetchFacilities({ venuePublicId, kind } = {}) {
  const res = await api.get('/v1/facilities', {
    params: { venue_public_id: venuePublicId, kind },
  })
  return res.data
}

export async function fetchManagerFacilities({ venuePublicId, kind } = {}) {
  const res = await api.get('/v1/manager/facilities', {
    params: { venue_public_id: venuePublicId, kind },
  })
  return res.data
}

export async function updateCourt(publicId, patch) {
  const res = await api.patch(`/v1/courts/${publicId}`, patch)
  return res.data
}

// --- Availability, pricing, slots ---------------------------------------

export async function fetchDayAvailability(courtPublicId, day) {
  const res = await api.get('/v1/availability/hours', {
    params: { court_public_id: courtPublicId, day },
  })
  return res.data
}

export async function fetchAvailabilityDates(courtPublicId, fromDay, toDay) {
  const res = await api.get('/v1/availability/dates', {
    params: { court_public_id: courtPublicId, from_day: fromDay, to_day: toDay },
  })
  return res.data
}

export async function fetchQuote(courtPublicId, startsAt, endsAt) {
  const res = await api.get('/v1/pricing/quote', {
    params: { court_public_id: courtPublicId, starts_at: startsAt, ends_at: endsAt },
  })
  return res.data
}

export async function generateSlots({ courtPublicId, fromDay, toDay }) {
  const res = await api.post('/v1/slots/generate', {
    court_public_id: courtPublicId,
    from_day: fromDay,
    to_day: toDay,
  })
  return res.data
}

// --- Bookings -----------------------------------------------------------

export async function createRangeBooking(payload) {
  const res = await api.post('/v1/bookings/range', payload)
  return res.data
}

export async function fetchBookingHistory(customerContact) {
  const res = await api.get('/v1/bookings', { params: { customer_contact: customerContact } })
  return res.data
}

// A manager token cancels anything; a customer must send the contact the
// booking was made with.
export async function cancelBookingGroup(groupPublicId, customerContact = '') {
  const res = await api.post(`/v1/bookings/groups/${groupPublicId}/cancel`, null, {
    params: customerContact ? { customer_contact: customerContact } : {},
  })
  return res.data
}

export async function confirmBookingGroup(groupPublicId) {
  const res = await api.post(`/v1/bookings/groups/${groupPublicId}/confirm`)
  return res.data
}

export async function markPaymentPaid(paymentPublicId) {
  const res = await api.post(`/v1/payments/${paymentPublicId}/mark-paid`)
  return res.data
}

// --- Payments -----------------------------------------------------------

export async function createPayment(bookingPublicId, { amount, kind = 'full' }) {
  const res = await api.post('/v1/payments', {
    booking_public_id: bookingPublicId,
    amount,
    kind,
  })
  return res.data
}

export async function fetchPayments(bookingPublicId) {
  const res = await api.get('/v1/payments', { params: { booking_public_id: bookingPublicId } })
  return res.data
}

// --- Manager ------------------------------------------------------------

export async function fetchManagerBookings(params = {}) {
  const res = await api.get('/v1/manager/bookings', { params })
  return res.data
}

export async function fetchManagerStats(params = {}) {
  const res = await api.get('/v1/manager/stats', { params })
  return res.data
}

export async function fetchOccupancy(fromDay, toDay) {
  const res = await api.get('/v1/manager/occupancy', {
    params: { from_day: fromDay, to_day: toDay },
  })
  return res.data
}

// --- Client settings ----------------------------------------------------

export async function fetchClientConfig() {
  const res = await api.get('/v1/config')
  return res.data
}

export default api
