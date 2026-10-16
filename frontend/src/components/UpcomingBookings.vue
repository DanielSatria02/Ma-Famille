<script setup>
import BookingCard from './BookingCard.vue'
import '../styles/todays-visitors.css'

defineProps({
  bookings: { type: Array, default: () => [] },
})

defineEmits(['cancel'])
</script>

<template>
  <section class="visitors" aria-labelledby="upcoming-title">
    <h2 id="upcoming-title" class="visitors-title">Upcoming Booking</h2>

    <ul v-if="bookings.length" class="visitors-list">
      <BookingCard
        v-for="booking in bookings"
        :key="booking.id"
        :booking="booking"
        cancellable
        @cancel="$emit('cancel', $event)"
      />
    </ul>
  </section>
</template>
