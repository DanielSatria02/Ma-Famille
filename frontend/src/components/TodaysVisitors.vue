<script setup>
import BookingCard from './BookingCard.vue'
import '../styles/todays-visitors.css'

defineProps({
  bookings: { type: Array, default: () => [] },
})

defineEmits(['confirm', 'markPaid'])
</script>

<template>
  <section class="visitors" aria-labelledby="visitors-title">
    <h2 id="visitors-title" class="visitors-title">Today's Visitors</h2>

    <ul v-if="bookings.length" class="visitors-list">
      <BookingCard
        v-for="booking in bookings"
        :key="booking.id"
        :booking="booking"
        manageable
        @confirm="$emit('confirm', $event)"
        @mark-paid="$emit('markPaid', $event)"
      />
    </ul>
  </section>
</template>
