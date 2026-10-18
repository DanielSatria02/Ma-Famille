<script setup>
import BookingCard from './BookingCard.vue'
import '../styles/todays-visitors.css'

defineProps({
  bookings: { type: Array, default: () => [] },
})

defineEmits(['cancel', 'confirm', 'markPaid'])
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
        manageable
        @cancel="$emit('cancel', $event)"
        @confirm="$emit('confirm', $event)"
        @mark-paid="$emit('markPaid', $event)"
      />
    </ul>
  </section>
</template>
