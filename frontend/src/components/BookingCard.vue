<script setup>
import '../styles/todays-visitors.css'

// booking: { id, date, startTime, endTime, visitorName, venueName }
// date is an ISO date string (e.g. "2026-10-22").
defineProps({
  booking: { type: Object, required: true },
  cancellable: { type: Boolean, default: false },
})

defineEmits(['cancel'])

function formatDate(date) {
  return new Date(`${date}T00:00`).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}
</script>

<template>
  <li class="visitor-card">
    <div class="visitor-info">
      <p class="visitor-schedule">
        {{ formatDate(booking.date) }} {{ booking.startTime }} - {{ booking.endTime }}
      </p>
      <p class="visitor-name">{{ booking.visitorName }}</p>
      <p class="visitor-venue">{{ booking.venueName }}</p>
    </div>
    <button v-if="cancellable" type="button" class="visitor-cancel" @click="$emit('cancel', booking)">
      Cancel
    </button>
  </li>
</template>
