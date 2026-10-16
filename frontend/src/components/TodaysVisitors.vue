<script setup>
import '../styles/todays-visitors.css'

// Each booking: { id, date, startTime, endTime, visitorName, venueName }
// date is an ISO date string (e.g. "2026-10-22"); the list is supplied by the API later.
defineProps({
  bookings: { type: Array, default: () => [] },
})

function formatDate(date) {
  return new Date(date).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}
</script>

<template>
  <section class="visitors" aria-labelledby="visitors-title">
    <h2 id="visitors-title" class="visitors-title">Today's Visitors</h2>

    <ul v-if="bookings.length" class="visitors-list">
      <li v-for="booking in bookings" :key="booking.id" class="visitor-card">
        <p class="visitor-schedule">
          {{ formatDate(booking.date) }} {{ booking.startTime }} - {{ booking.endTime }}
        </p>
        <p class="visitor-name">{{ booking.visitorName }}</p>
        <p class="visitor-venue">{{ booking.venueName }}</p>
      </li>
    </ul>
  </section>
</template>
