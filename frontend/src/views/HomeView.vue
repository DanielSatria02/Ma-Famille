<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import BookingCalendar from '../components/BookingCalendar.vue'
import LocationPanel from '../components/LocationPanel.vue'
import VenueCard from '../components/VenueCard.vue'
import { addDays, toIsoDate } from '../utils/date.js'
import { errorDetail, fetchAvailabilityDates, fetchVenueHours, fetchVenues } from '../services/api.js'
import { useVenuesStore } from '../stores/venues.js'

const router = useRouter()
const venuesStore = useVenuesStore()

const venue = ref(null)
const venueHours = ref([])
const error = ref('')
// Dates stay hidden until the client checks availability.
const availabilityChecked = ref(false)
const fullyBookedDates = ref([])

// Monday-first index, like the backend's day_of_week.
const todayIndex = (new Date().getDay() + 6) % 7
const todayHours = computed(
  () => venueHours.value.find((entry) => entry.day_of_week === todayIndex) ?? null,
)
const firstBookable = computed(
  () => venuesStore.facilities.find((facility) => facility.is_bookable) ?? null,
)

onMounted(async () => {
  await venuesStore.load()
  try {
    const venues = await fetchVenues()
    venue.value = venues[0] ?? null
    if (venue.value) venueHours.value = await fetchVenueHours(venue.value.public_id)
  } catch (err) {
    error.value = errorDetail(err, 'Could not load the venue.')
  }
})

// A date nobody can book (no free hour) is greyed out on the calendar.
async function checkAvailability() {
  availabilityChecked.value = true
  if (!firstBookable.value) {
    fullyBookedDates.value = []
    return
  }
  try {
    const from = toIsoDate(new Date())
    const to = toIsoDate(addDays(new Date(), 30))
    const days = await fetchAvailabilityDates(firstBookable.value.public_id, from, to)
    fullyBookedDates.value = days.filter((day) => day.free_hours === 0).map((day) => day.day)
  } catch (err) {
    error.value = errorDetail(err, 'Could not load availability.')
    fullyBookedDates.value = []
  }
}

function goToBooking(date) {
  router.push({ name: 'booking', query: { date } })
}
</script>

<template>
  <section class="space-y-4">
    <BookingCalendar
      :booked-dates="availabilityChecked ? fullyBookedDates : []"
      :bookable="availabilityChecked"
      @book="goToBooking"
    />
    <LocationPanel />
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
    <VenueCard
      :title="venue?.name ?? 'Ma-Famille'"
      :location="venue?.address ?? ''"
      :tags="venue?.tags ?? []"
      :open-time="todayHours?.is_closed ? 'Closed today' : todayHours?.opens_at ?? ''"
      :close-time="todayHours?.is_closed ? '' : todayHours?.closes_at ?? ''"
      @check-availability="checkAvailability"
    />
  </section>
</template>
