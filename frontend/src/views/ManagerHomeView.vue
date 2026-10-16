<script setup>
import { computed, ref } from 'vue'
import BookingCalendar from '../components/BookingCalendar.vue'
import OpeningSchedule from '../components/OpeningSchedule.vue'
import PricingSettings from '../components/PricingSettings.vue'
import StatsOverview from '../components/StatsOverview.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
import UnavailableNotice from '../components/UnavailableNotice.vue'
import UpcomingBookings from '../components/UpcomingBookings.vue'
import VenueStatus from '../components/VenueStatus.vue'

// Filled from the bookings API once it is available.
const todaysBookings = ref([])
const upcomingBookings = ref([])
const weeklyVisitors = ref(0)
const canceledBookings = ref(0)

// Default hours; to be loaded from and saved to the API later.
const openingSchedule = ref(
  ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map((day) => ({
    day,
    start: '04:00',
    end: '23:00',
  })),
)

function cancelBooking(booking) {
  upcomingBookings.value = upcomingBookings.value.filter((item) => item.id !== booking.id)
  canceledBookings.value += 1
  weeklyVisitors.value = Math.max(0, weeklyVisitors.value - 1)
}

function updateSchedule({ day, start, end }) {
  const entry = openingSchedule.value.find((item) => item.day === day)
  if (entry) Object.assign(entry, { start, end })
}

// Stored hourly prices; null means no price set (unavailable for booking, not free).
// To be loaded from and saved to the API later.
const prices = ref({ arena: 100000, office: 100000 })

const venues = ref([
  { key: 'cafe', label: 'Cafe', available: true },
  { key: 'office', label: 'Office', available: true },
  { key: 'arena', label: 'Padel Arena', available: true },
])

// An unavailable venue shows no price, so the booking page can say "unavailable" for it.
const pricing = computed(() =>
  [
    { key: 'arena', label: 'Arena' },
    { key: 'office', label: 'Office' },
  ].map((item) => {
    const venue = venues.value.find((entry) => entry.key === item.key)
    return { ...item, price: venue?.available ? prices.value[item.key] : null }
  }),
)

const venueStatusItems = computed(() =>
  venues.value.map((venue) => ({
    ...venue,
    locked: venue.key in prices.value && prices.value[venue.key] === null,
  })),
)

function updatePricing({ key, price }) {
  const venue = venues.value.find((entry) => entry.key === key)
  if (!venue) return
  if (price === null) {
    prices.value[key] = null
    venue.available = false
    return
  }
  // Setting a price after a reset brings the venue back.
  if (prices.value[key] === null) venue.available = true
  prices.value[key] = price
}

function toggleVenue({ key, available }) {
  const venue = venues.value.find((entry) => entry.key === key)
  if (venue) venue.available = available
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
    <BookingCalendar allow-past-months />
    <TodaysVisitors :bookings="todaysBookings" />
    <UpcomingBookings :bookings="upcomingBookings" @cancel="cancelBooking" />
    <OpeningSchedule :schedule="openingSchedule" @update="updateSchedule" />
    <PricingSettings :items="pricing" @update="updatePricing" />
    <VenueStatus :venues="venueStatusItems" @toggle="toggleVenue" />
  </section>
</template>
