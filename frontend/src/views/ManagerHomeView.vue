<script setup>
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import BookingCalendar from '../components/BookingCalendar.vue'
import OpeningSchedule from '../components/OpeningSchedule.vue'
import PricingSettings from '../components/PricingSettings.vue'
import StatsOverview from '../components/StatsOverview.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
import UnavailableNotice from '../components/UnavailableNotice.vue'
import UpcomingBookings from '../components/UpcomingBookings.vue'
import VenueStatus from '../components/VenueStatus.vue'
import { useBookingsStore } from '../stores/bookings.js'
import { useVenuesStore } from '../stores/venues.js'

const bookingsStore = useBookingsStore()
const { todaysBookings, upcomingBookings, bookedDates, weeklyVisitors, canceledCount: canceledBookings } =
  storeToRefs(bookingsStore)

const venuesStore = useVenuesStore()
const { venues, pricing, venueStatusItems } = storeToRefs(venuesStore)

// Default hours; to be loaded from and saved to the API later.
const openingSchedule = ref(
  ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map((day) => ({
    day,
    start: '04:00',
    end: '23:00',
  })),
)

function cancelBooking(booking) {
  bookingsStore.cancelBooking(booking.id)
}

function updateSchedule({ day, start, end }) {
  const entry = openingSchedule.value.find((item) => item.day === day)
  if (entry) Object.assign(entry, { start, end })
}
</script>

<template>
  <section class="space-y-4">
    <StatsOverview
      :weekly-visitors="weeklyVisitors"
      :todays-bookings="todaysBookings.length"
      :canceled-bookings="canceledBookings"
    />
    <UnavailableNotice :venues="venues" />
    <BookingCalendar allow-past-months :booked-dates="bookedDates" />
    <TodaysVisitors :bookings="todaysBookings" />
    <UpcomingBookings :bookings="upcomingBookings" @cancel="cancelBooking" />
    <OpeningSchedule :schedule="openingSchedule" @update="updateSchedule" />
    <PricingSettings :items="pricing" @update="venuesStore.updatePricing" />
    <VenueStatus :venues="venueStatusItems" @toggle="venuesStore.toggleVenue" />
  </section>
</template>
