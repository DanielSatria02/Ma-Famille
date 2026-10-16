<script setup>
import { ref } from 'vue'
import BookingCalendar from '../components/BookingCalendar.vue'
import OpeningSchedule from '../components/OpeningSchedule.vue'
import StatsOverview from '../components/StatsOverview.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
import UpcomingBookings from '../components/UpcomingBookings.vue'

// Filled from the bookings API once it is available.
const todaysBookings = ref([])
const upcomingBookings = ref([])
const weeklyVisitors = ref(0)
const canceledBookings = ref(0)

// Default hours; to be loaded from and saved to the API later.
const openingSchedule = ref(
  ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map((day) => ({
    day,
    start: '04:00',
    end: '23:00',
  })),
)

function cancelBooking(booking) {
  upcomingBookings.value = upcomingBookings.value.filter((item) => item.id !== booking.id)
  canceledBookings.value += 1
  weeklyVisitors.value = Math.max(0, weeklyVisitors.value - 1)
}

function updateSchedule({ day, start, end }) {
  const entry = openingSchedule.value.find((item) => item.day === day)
  if (entry) Object.assign(entry, { start, end })
}
</script>

<template>
  <section class="space-y-4">
    <StatsOverview
      :weekly-visitors="weeklyVisitors"
      :todays-bookings="todaysBookings.length"
      :canceled-bookings="canceledBookings"
    />
    <BookingCalendar allow-past-months />
    <TodaysVisitors :bookings="todaysBookings" />
    <UpcomingBookings :bookings="upcomingBookings" @cancel="cancelBooking" />
    <OpeningSchedule :schedule="openingSchedule" @update="updateSchedule" />
  </section>
</template>
