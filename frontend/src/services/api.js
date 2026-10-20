import axios from 'axios'

import { getCustomerToken, getManagerToken } from './session.js'

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

// Manager routes want `X-Manager-Token`; customer routes want `X-Customer-Token`.
// One interceptor covers every call, so no caller has to remember either.
api.interceptors.request.use((config) => {
  const token = getManagerToken()
  if (token) config.headers['X-Manager-Token'] = token
  const customerToken = getCustomerToken()
  if (customerToken) config.headers['X-Customer-Token'] = customerToken
  return config
})

// The backend puts a human-readable reason in `detail`; surface it verbatim.
//
// A crash on the server comes back as JSON with a request id, and the id is
// what ties the message on the screen to the line in the server log. It is
// only useful if it is shown, so it is appended rather than left in the
// network panel.
export function errorDetail(error, fallback = 'Something went wrong.') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return withRequestId(error, detail)
  if (error?.response?.status === 401) return 'Please log in as manager first.'
  // No response at all: the request never got an answer. Either the server is
  // down, or the browser blocked the answer — which is what happened when a
  // crash came back without CORS headers.
  if (!error?.response) return 'The server is not reachable.'
  return withRequestId(error, fallback)
}

function withRequestId(error, message) {
  const requestId = error?.response?.data?.request_id
  return requestId ? `${message} (reference ${requestId})` : message
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

// Put the session token on the backend deny-list. Only worth calling when a
// token exists (local open-access dev has none) — see the auth store.
export async function logoutManager() {
  const res = await api.post('/v1/auth/logout')
  return res.data
}

// --- Customer accounts ----------------------------------------------------

// Both answers carry the token in the body and in `X-Customer-Token`; the
// body is what we read.
export async function registerCustomer({ email, password, displayName, phone = '' }) {
  const res = await api.post('/v1/customers/register', {
    email,
    password,
    display_name: displayName,
    phone,
  })
  return res.data
}

export async function loginCustomer({ email, password }) {
  const res = await api.post('/v1/customers/login', { email, password })
  return res.data
}

export async function logoutCustomer() {
  const res = await api.post('/v1/customers/logout')
  return res.data
}

export async function fetchMe() {
  const res = await api.get('/v1/customers/me')
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

// The free hours of a whole club, across all of its courts.
export async function fetchVenueAvailabilityDates(venuePublicId, fromDay, toDay) {
  const res = await api.get('/v1/availability/dates', {
    params: { venue_public_id: venuePublicId, from_day: fromDay, to_day: toDay },
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

export async function fetchBookingHistory(customerContact, { limit, offset } = {}) {
  return getPaged('/v1/bookings', {
    customer_contact: customerContact,
    ...(limit ? { limit } : {}),
    ...(offset ? { offset } : {}),
  })
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

// --- Promo codes ---------------------------------------------------------

// The public dry run: what would this code do to that range, right now? Writes
// nothing. The booking re-verifies the code anyway, so this only feeds the UI.
export async function checkPromotion({ code, courtPublicId, startsAt, endsAt } = {}) {
  const res = await api.get('/v1/promotions/check', {
    params: {
      code,
      ...(courtPublicId ? { court_public_id: courtPublicId } : {}),
      ...(startsAt ? { starts_at: startsAt } : {}),
      ...(endsAt ? { ends_at: endsAt } : {}),
    },
  })
  return res.data
}

export async function fetchPromotions(params = {}) {
  const res = await api.get('/v1/promotions', { params })
  return res.data
}

export async function createPromotion(payload) {
  const res = await api.post('/v1/promotions', payload)
  return res.data
}

export async function updatePromotion(publicId, payload) {
  const res = await api.patch(`/v1/promotions/${publicId}`, payload)
  return res.data
}

// A redeemed code answers 409 — it stays as evidence of what was charged.
// Switch it off instead of deleting it.
export async function deletePromotion(publicId) {
  const res = await api.delete(`/v1/promotions/${publicId}`)
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

// Lists that page keep the plain JSON array; the total rides in
// `X-Total-Count` (exposed through CORS) so the client can offer next/prev
// without the payload changing shape.
async function getPaged(url, params) {
  const res = await api.get(url, { params })
  const total = Number(res.headers?.['x-total-count'])
  return { rows: res.data, total: Number.isFinite(total) ? total : res.data.length }
}

// --- Manager ------------------------------------------------------------

export async function fetchManagerBookings(params = {}) {
  return getPaged('/v1/manager/bookings', params)
}

// Who changed what, newest first. Narrow it with entity_type (venue, court,
// booking…), action (payment.refund…) or actor.
export async function fetchAuditEvents(params = {}) {
  return getPaged('/v1/manager/audit', params)
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

// --- Reviews ------------------------------------------------------------

// A rating is only accepted from someone whose visit has already happened, so
// the UI asks for the contact when the visitor is not signed in — the same
// proof they use to cancel a visit.
export async function fetchRatingSummary(venuePublicId) {
  const res = await api.get('/v1/reviews/summary', {
    params: { venue_public_id: venuePublicId },
  })
  return res.data
}

export async function fetchReviews(venuePublicId, { limit, offset } = {}) {
  return getPaged('/v1/reviews', {
    venue_public_id: venuePublicId,
    ...(limit ? { limit } : {}),
    ...(offset ? { offset } : {}),
  })
}

export async function writeReview(venuePublicId, { rating, comment, customerContact }) {
  const res = await api.post('/v1/reviews', {
    venue_public_id: venuePublicId,
    rating,
    comment: comment || null,
  }, {
    params: customerContact ? { customer_contact: customerContact } : {},
  })
  return res.data
}

// --- Client settings ----------------------------------------------------

export async function fetchClientConfig() {
  const res = await api.get('/v1/config')
  return res.data
}

export default api
