import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { addDays, toIsoDate } from '../utils/date.js'

// Single source of truth for bookings, shared by the manager and client pages.
// booking: { id, date: "YYYY-MM-DD", startTime, endTime, visitorName, venueName }
// Bookings are loaded from the API once it is available.
export const useBookingsStore = defineStore('bookings', () => {
  const bookings = ref([])
  const canceledCount = ref(0)

  const todaysBookings = computed(() => bookings.value.filter((b) => b.date === toIsoDate(new Date())))
  const upcomingBookings = computed(() =>
    bookings.value.filter((b) => b.date === toIsoDate(addDays(new Date(), 1))),
  )
  const bookedDates = computed(() => [...new Set(bookings.value.map((b) => b.date))])
  const weeklyVisitors = computed(() => bookings.value.length)

  function cancelBooking(id) {
    const before = bookings.value.length
    bookings.value = bookings.value.filter((b) => b.id !== id)
    if (bookings.value.length < before) canceledCount.value += 1
  }

  return {
    bookings,
    canceledCount,
    todaysBookings,
    upcomingBookings,
    bookedDates,
    weeklyVisitors,
    cancelBooking,
  }
})
