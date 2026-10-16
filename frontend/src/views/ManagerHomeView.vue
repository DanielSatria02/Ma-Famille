<script setup>
import BookingCalendar from '../components/BookingCalendar.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
</script>

<template>
  <section class="space-y-4">
    <BookingCalendar allow-past-months />
    <TodaysVisitors />
  </section>
</template>
