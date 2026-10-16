<script setup>
import { ref } from 'vue'
import BookingCalendar from '../components/BookingCalendar.vue'
import OpeningSchedule from '../components/OpeningSchedule.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
import UpcomingBookings from '../components/UpcomingBookings.vue'

// Filled from the bookings API once it is available.
const todaysBookings = ref([])
const upcomingBookings = ref([])

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
}

function updateSchedule({ day, start, end }) {
  const entry = openingSchedule.value.find((item) => item.day === day)
  if (entry) Object.assign(entry, { start, end })
}
</script>

<template>
  <section class="space-y-4">
    <BookingCalendar allow-past-months />
    <TodaysVisitors :bookings="todaysBookings" />
    <UpcomingBookings :bookings="upcomingBookings" @cancel="cancelBooking" />
    <OpeningSchedule :schedule="openingSchedule" @update="updateSchedule" />
  </section>
</template>
