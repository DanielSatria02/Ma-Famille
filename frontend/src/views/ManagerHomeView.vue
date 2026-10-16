<script setup>
import { ref } from 'vue'
import BookingCalendar from '../components/BookingCalendar.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
import UpcomingBookings from '../components/UpcomingBookings.vue'

// Filled from the bookings API once it is available.
const todaysBookings = ref([])
const upcomingBookings = ref([])

function cancelBooking(booking) {
  upcomingBookings.value = upcomingBookings.value.filter((item) => item.id !== booking.id)
}
</script>

<template>
  <section class="space-y-4">
    <BookingCalendar allow-past-months />
    <TodaysVisitors :bookings="todaysBookings" />
    <UpcomingBookings :bookings="upcomingBookings" @cancel="cancelBooking" />
  </section>
</template>
