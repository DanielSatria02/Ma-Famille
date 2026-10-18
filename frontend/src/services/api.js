import axios from 'axios'

import { getManagerToken } from './session.js'

// Where the API lives. Media URLs come back as paths (`/media/…`), so the client
// needs the origin to turn them into something an <img> can load.
export const API_ORIGIN = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(
  /\/$/,
  '',
)

const api = axios.create({
  baseURL: API_ORIGIN,
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

export async function updateVenue(publicId, patch) {
  const res = await api.patch(`/v1/venues/${publicId}`, patch)
  return res.data
}

// Photos travel as the raw file body (no multipart), the same shape the backend
// accepts: /venues/{id}/photo and /courts/{id}/photo.
function photoConfig(file) {
  return {
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
    timeout: 20000,
  }
}

export async function uploadVenuePhoto(publicId, file) {
  const res = await api.put(`/v1/venues/${publicId}/photo`, file, photoConfig(file))
  return res.data
}

export async function removeVenuePhoto(publicId) {
  const res = await api.delete(`/v1/venues/${publicId}/photo`)
  return res.data
}

export async function uploadCourtPhoto(publicId, file) {
  const res = await api.put(`/v1/courts/${publicId}/photo`, file, photoConfig(file))
  return res.data
}

export async function removeCourtPhoto(publicId) {
  const res = await api.delete(`/v1/courts/${publicId}/photo`)
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

// Close or reopen a window of hours ("facility shut 09:00-12:00 on Saturday").
// Booked hours are never touched; the response counts what was skipped.
export async function blockSlots({
  facilityPublicId,
  venuePublicId,
  fromDay,
  toDay,
  fromHour,
  toHour,
  status = 'blocked',
}) {
  const res = await api.post('/v1/slots/block', {
    court_public_id: facilityPublicId ?? null,
    venue_public_id: venuePublicId ?? null,
    from_day: fromDay,
    to_day: toDay,
    from_hour: fromHour,
    to_hour: toHour,
    status,
  })
  return res.data
}

export async function fetchVenueClosures(venuePublicId) {
  const res = await api.get(`/v1/venues/${venuePublicId}/closures`)
  return res.data
}

export async function createVenueClosure(venuePublicId, { startsOn, endsOn, reason = '' }) {
  const res = await api.post(`/v1/venues/${venuePublicId}/closures`, {
    starts_on: startsOn,
    ends_on: endsOn,
    reason,
  })
  return res.data
}

export async function deleteVenueClosure(venuePublicId, closurePublicId) {
  const res = await api.delete(`/v1/venues/${venuePublicId}/closures/${closurePublicId}`)
  return res.data
}

// --- Bookings -----------------------------------------------------------

export async function createRangeBooking(payload) {
  const res = await api.post('/v1/bookings/range', payload)
  return res.data
}

export async function fetchBooking(publicId) {
  const res = await api.get(`/v1/bookings/${publicId}`)
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

// Returns { payment, provider: 'doku'|'local', detail } — `local` means the books
// were corrected but no money moved (no DOKU keys), so never show it as refunded
// by the provider.
export async function refundPayment(paymentPublicId) {
  const res = await api.post(`/v1/payments/${paymentPublicId}/refund`)
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

export async function fetchNotifications(params = {}) {
  const res = await api.get('/v1/manager/notifications', { params })
  return res.data
}

export async function dispatchNotifications(limit = 20) {
  const res = await api.post('/v1/manager/notifications/dispatch', null, { params: { limit } })
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
