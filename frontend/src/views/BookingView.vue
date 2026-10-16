<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import BookingForm from '../components/BookingForm.vue'

const route = useRoute()

// Set when arriving from a double-click on the home calendar; invalid dates are ignored by the form.
const initialDate = computed(() => (typeof route.query.date === 'string' ? route.query.date : ''))
</script>

<template>
  <section class="space-y-6">
    <h1 class="text-center text-3xl font-bold tracking-tight text-gray-900">Book your Venue</h1>
    <BookingForm :initial-date="initialDate" />
  </section>
</template>
