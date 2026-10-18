import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  cancelBookingGroup,
  confirmBookingGroup,
  errorDetail,
  fetchManagerBookings,
  fetchManagerStats,
  markPaymentPaid,
  refundPayment,
} from '../services/api.js'
import { addDays, toIsoDate } from '../utils/date.js'

const dateOf = (value) => String(value ?? '').slice(0, 10)
const timeOf = (value) => String(value ?? '').slice(11, 16)

// Manager booking rows, straight from `/manager/bookings` (one row per booked
// hour, with slot/court/venue embedded by the API).
// booking: { id, groupId, date, startTime, endTime, visitorName, venueName, status, total,
//            paymentStatus: 'unpaid'|'paid'|'refunded', paymentIds: [], invoice }
export const useBookingsStore = defineStore('bookings', () => {
  const bookings = ref([])
  const stats = ref({ todays_bookings: 0, weekly_visitors: 0, cancelled_bookings: 0 })
  const loading = ref(false)
  const error = ref('')
  // Something honest to tell the manager that is not an error (e.g. a refund that
  // only corrected the books because no gateway is configured).
  const notice = ref('')
  const window = ref({ fromDay: '', toDay: '' })

  const isActive = (booking) => booking.status !== 'cancelled'

  // Money is per hour, so the visit label is derived from the hours, not from the
  // last row read: all paid → paid, every hour either paid or refunded → refunded,
  // anything still open → part paid.
  function paymentSummary(visit) {
    const { hours, paidHours, refundedHours, failedHours } = visit
    const settled = paidHours + refundedHours === hours
    let paymentStatus = 'unpaid'
    if (paidHours === hours) paymentStatus = 'paid'
    else if (settled && refundedHours > 0) paymentStatus = 'refunded'
    else if (paidHours > 0 || refundedHours > 0) paymentStatus = 'partial'
    else if (failedHours > 0) paymentStatus = 'failed'
    return { paymentStatus, refundable: paidHours > 0 }
  }

  // One visit = one booking group; the lists show visits, not hours.
  function visits(rows) {
    const byGroup = new Map()
    for (const row of rows) {
      const key = row.groupId ?? row.id
      let visit = byGroup.get(key)
      if (!visit) {
        visit = {
          ...row,
          id: key,
          hours: 0,
          total: 0,
          paidHours: 0,
          refundedHours: 0,
          failedHours: 0,
          paymentIds: [...row.paymentIds],
        }
        byGroup.set(key, visit)
      } else {
        visit.startTime = visit.startTime < row.startTime ? visit.startTime : row.startTime
        visit.endTime = visit.endTime > row.endTime ? visit.endTime : row.endTime
        visit.paymentIds = [...new Set([...visit.paymentIds, ...row.paymentIds])]
        if (!visit.paymentNote && row.paymentNote) visit.paymentNote = row.paymentNote
        if (!visit.invoice && row.invoice) visit.invoice = row.invoice
      }
      visit.hours += 1
      visit.total += row.total
      if (row.paymentStatus === 'paid') visit.paidHours += 1
      else if (row.paymentStatus === 'refunded') visit.refundedHours += 1
      else if (row.paymentStatus === 'failed') visit.failedHours += 1
    }
    return [...byGroup.values()]
      .map((visit) => ({ ...visit, ...paymentSummary(visit) }))
      .sort((a, b) => `${a.date}${a.startTime}`.localeCompare(`${b.date}${b.startTime}`))
  }

  const todaysBookings = computed(() =>
    bookings.value.filter((booking) => isActive(booking) && booking.date === toIsoDate(new Date())),
  )
  const upcomingBookings = computed(() => {
    const tomorrow = toIsoDate(addDays(new Date(), 1))
    return visits(bookings.value.filter((booking) => isActive(booking) && booking.date === tomorrow))
  })
  const bookedDates = computed(() => [
    ...new Set(bookings.value.filter(isActive).map((booking) => booking.date)),
  ])
  const weeklyVisitors = computed(() => stats.value.weekly_visitors ?? 0)
  const canceledCount = computed(() => stats.value.cancelled_bookings ?? 0)

  // The backend pages at 50 rows and reports the real total in `X-Total-Count`.
  // Without it a busy window would quietly show only the first page and look
  // like the whole day.
  const PAGE_SIZE = 50
  const totalBookings = ref(0)
  const hasMore = computed(() => bookings.value.length < totalBookings.value)

  const toVisitRow = (row) => ({
    id: row.public_id,
    groupId: row.group_public_id ?? row.public_id,
    date: dateOf(row.slot?.starts_at),
    startTime: timeOf(row.slot?.starts_at),
    endTime: timeOf(row.slot?.ends_at),
    visitorName: row.customer_name,
    contact: row.customer_contact,
    venueName: row.court?.name ?? '',
    place: row.venue?.name ?? '',
    status: row.status,
    total: row.total ?? 0,
    paymentStatus: row.payment_status ?? 'unpaid',
    paymentIds: row.payment_public_id ? [row.payment_public_id] : [],
    paymentNote: row.payment_failure_reason ?? '',
    invoice: row.payment_invoice_number ?? '',
  })

  async function load({ day = '', fromDay = '', toDay = '' } = {}) {
    loading.value = true
    window.value = { fromDay: fromDay || day, toDay: toDay || day }
    try {
      const [page, counters] = await Promise.all([
        fetchManagerBookings({
          day: day || undefined,
          from_day: fromDay || undefined,
          to_day: toDay || undefined,
          limit: PAGE_SIZE,
          offset: 0,
        }),
        fetchManagerStats({ day: day || undefined }),
      ])
      totalBookings.value = page.total
      bookings.value = page.rows.map(toVisitRow)
      stats.value = counters
      error.value = ''
    } catch (err) {
      error.value = errorDetail(err, 'Could not load the bookings.')
    } finally {
      loading.value = false
    }
  }

  // One more page of the same window, appended and de-duplicated by id.
  async function loadMore() {
    if (loading.value || !hasMore.value) return
    loading.value = true
    try {
      const page = await fetchManagerBookings({
        day:
          window.value.fromDay && window.value.fromDay === window.value.toDay
            ? window.value.fromDay
            : undefined,
        from_day: window.value.fromDay || undefined,
        to_day: window.value.toDay || undefined,
        limit: PAGE_SIZE,
        offset: bookings.value.length,
      })
      const seen = new Set(bookings.value.map((row) => row.id))
      bookings.value = [
        ...bookings.value,
        ...page.rows.map(toVisitRow).filter((row) => !seen.has(row.id)),
      ]
      totalBookings.value = page.total
    } catch (err) {
      error.value = errorDetail(err, 'Could not load the next page.')
    } finally {
      loading.value = false
    }
  }

  // Cancels the whole visit (every hour of the group) and reloads the window.
  // Lists show visits keyed by the group id, single rows by their booking id.
  function findVisit(id) {
    return bookings.value.find((booking) => booking.id === id || booking.groupId === id)
  }

  async function cancelBooking(id) {
    const row = findVisit(id)
    if (!row) return
    error.value = ''
    try {
      await cancelBookingGroup(row.groupId)
      await load({ fromDay: window.value.fromDay, toDay: window.value.toDay })
    } catch (err) {
      error.value = errorDetail(err, 'Could not cancel the booking.')
    }
  }

  // Confirms every hour of a visit (the deposit/offline payment arrived).
  async function confirmVisit(id) {
    const row = findVisit(id)
    if (!row) return
    error.value = ''
    try {
      await confirmBookingGroup(row.groupId)
      await load({ fromDay: window.value.fromDay, toDay: window.value.toDay })
    } catch (err) {
      error.value = errorDetail(err, 'Could not confirm the visit.')
    }
  }

  // Marks the invoices of a visit as paid; the backend confirms the booking too.
  async function markVisitPaid(id) {
    const row = findVisit(id)
    if (!row) return
    error.value = ''
    notice.value = ''
    if (!row.paymentIds.length) {
      error.value = 'That visit has no invoice yet, so there is nothing to mark as paid.'
      return
    }
    try {
      for (const paymentId of row.paymentIds) {
        await markPaymentPaid(paymentId)
      }
      await load({ fromDay: window.value.fromDay, toDay: window.value.toDay })
    } catch (err) {
      error.value = errorDetail(err, 'Could not mark the payment as paid.')
    }
  }

  // Sends the money back for the hours that were paid. The backend tells us whether a
  // provider actually moved it: with no DOKU keys the books are corrected and the cash
  // is still on the manager. Hours with nothing to refund answer 409 and are skipped.
  async function refundVisit(id) {
    const row = findVisit(id)
    if (!row) return
    error.value = ''
    notice.value = ''
    if (!row.paymentIds.length) {
      error.value = 'That visit has no invoice, so there is nothing to refund.'
      return
    }
    let refunded = 0
    let skipped = 0
    let local = false
    try {
      for (const paymentId of row.paymentIds) {
        try {
          const result = await refundPayment(paymentId)
          refunded += 1
          if (result.provider === 'local') local = true
        } catch (err) {
          if (err?.response?.status === 409) {
            skipped += 1
            continue
          }
          throw err
        }
      }
      await load({ fromDay: window.value.fromDay, toDay: window.value.toDay })
      const parts = [`${refunded} payment(s) refunded`]
      if (skipped) parts.push(`${skipped} had nothing to refund`)
      parts.push(
        local
          ? 'there are no DOKU keys, so the money itself has to be returned by hand'
          : 'DOKU accepted the refund',
      )
      notice.value = `${parts.join('; ')}.`
    } catch (err) {
      error.value = errorDetail(err, 'Could not refund the payment.')
    }
  }

  return {
    bookings,
    stats,
    loading,
    error,
    notice,
    todaysBookings,
    upcomingBookings,
    bookedDates,
    weeklyVisitors,
    canceledCount,
    totalBookings,
    hasMore,
    load,
    loadMore,
    cancelBooking,
    confirmVisit,
    markVisitPaid,
    refundVisit,
  }
})
