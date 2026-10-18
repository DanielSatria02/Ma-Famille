import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  cancelBookingGroup,
  confirmBookingGroup,
  errorDetail,
  fetchManagerBookings,
  fetchManagerStats,
  markPaymentPaid,
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
  const window = ref({ fromDay: '', toDay: '' })

  const isActive = (booking) => booking.status !== 'cancelled'

  // One visit = one booking group; the lists show visits, not hours.
  function visits(rows) {
    const byGroup = new Map()
    for (const row of rows) {
      const key = row.groupId ?? row.id
      const visit = byGroup.get(key)
      if (!visit) {
        byGroup.set(key, { ...row, id: key, hours: 1, paymentIds: [...row.paymentIds] })
        continue
      }
      visit.startTime = visit.startTime < row.startTime ? visit.startTime : row.startTime
      visit.endTime = visit.endTime > row.endTime ? visit.endTime : row.endTime
      visit.hours += 1
      visit.total += row.total
      // A visit counts as paid only when every hour of it is paid.
      visit.paymentIds = [...new Set([...visit.paymentIds, ...row.paymentIds])]
      if (visit.paymentStatus !== row.paymentStatus) visit.paymentStatus = 'partial'
      if (!visit.invoice && row.invoice) visit.invoice = row.invoice
    }
    return [...byGroup.values()].sort((a, b) =>
      `${a.date}${a.startTime}`.localeCompare(`${b.date}${b.startTime}`),
    )
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

  async function load({ day = '', fromDay = '', toDay = '' } = {}) {
    loading.value = true
    window.value = { fromDay: fromDay || day, toDay: toDay || day }
    try {
      const [rows, counters] = await Promise.all([
        fetchManagerBookings({ day: day || undefined, from_day: fromDay || undefined, to_day: toDay || undefined }),
        fetchManagerStats({ day: day || undefined }),
      ])
      bookings.value = rows.map((row) => ({
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
        invoice: row.payment_invoice_number ?? '',
      }))
      stats.value = counters
      error.value = ''
    } catch (err) {
      error.value = errorDetail(err, 'Could not load the bookings.')
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

  return {
    bookings,
    stats,
    loading,
    error,
    todaysBookings,
    upcomingBookings,
    bookedDates,
    weeklyVisitors,
    canceledCount,
    load,
    cancelBooking,
    confirmVisit,
    markVisitPaid,
  }
})
