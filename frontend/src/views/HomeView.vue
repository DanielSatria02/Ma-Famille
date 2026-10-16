<script setup>
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import BookingCalendar from '../components/BookingCalendar.vue'
import LocationPanel from '../components/LocationPanel.vue'
import VenueCard from '../components/VenueCard.vue'
import { useBookingsStore } from '../stores/bookings.js'

const router = useRouter()
const { bookedDates: allBookedDates } = storeToRefs(useBookingsStore())

// Dates stay hidden until the client checks availability.
const availabilityChecked = ref(false)

function checkAvailability() {
  availabilityChecked.value = true
}

function goToBooking(date) {
  router.push({ name: 'booking', query: { date } })
}
</script>

<template>
  <section class="space-y-4">
    <BookingCalendar
      :booked-dates="availabilityChecked ? allBookedDates : []"
      :bookable="availabilityChecked"
      @book="goToBooking"
    />
    <LocationPanel />
    <VenueCard @check-availability="checkAvailability" />
  </section>
</template>
