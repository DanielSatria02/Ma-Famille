<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BookingCalendar from '../components/BookingCalendar.vue'
import LocationPanel from '../components/LocationPanel.vue'
import VenueCard from '../components/VenueCard.vue'
import { addDays, toIsoDate } from '../utils/date.js'
import { errorDetail, fetchAvailabilityDates, fetchVenueHours, fetchVenues } from '../services/api.js'
import { useVenuesStore } from '../stores/venues.js'

const KIND_LABELS = { court: 'Court', office: 'Private Office', cafe: 'Cafe' }

const router = useRouter()
const venuesStore = useVenuesStore()

const venues = ref([])
const hoursByVenue = ref({})
const filters = ref({ kind: [], tag: [] })
const selectedKey = ref('')
// The calendar only shows dates for a facility the client has asked about.
const checkedKey = ref('')
const fullyBookedDates = ref([])
const loading = ref(false)
const error = ref('')

const facilities = computed(() => venuesStore.facilities)
const venueOf = (facility) =>
  venues.value.find((venue) => venue.public_id === facility?.venue?.public_id) ?? null
const tagsOf = (facility) => venueOf(facility)?.tags ?? []

// Only the kinds and tags actually in use are offered as filters.
const filterGroups = computed(() => {
  const kinds = [...new Set(facilities.value.map((facility) => facility.kind))]
  const tags = [...new Set(venues.value.flatMap((venue) => venue.tags ?? []))].sort()
  const groups = []
  if (kinds.length) {
    groups.push({
      key: 'kind',
      title: 'Venue Type',
      options: kinds.map((kind) => ({ value: kind, label: KIND_LABELS[kind] ?? kind })),
    })
  }
  if (tags.length) {
    groups.push({
      key: 'tag',
      title: 'Area & Use',
      options: tags.map((tag) => ({ value: tag, label: tag })),
    })
  }
  return groups
})

const visibleFacilities = computed(() =>
  facilities.value.filter((facility) => {
    const kinds = filters.value.kind ?? []
    const tags = filters.value.tag ?? []
    if (kinds.length && !kinds.includes(facility.kind)) return false
    if (tags.length && !tags.some((tag) => tagsOf(facility).includes(tag))) return false
    return true
  }),
)

const selected = computed(
  () => facilities.value.find((facility) => facility.public_id === selectedKey.value) ?? null,
)
const availabilityChecked = computed(
  () => Boolean(checkedKey.value) && checkedKey.value === selectedKey.value,
)

// Monday-first index, like the backend's day_of_week.
const todayIndex = (new Date().getDay() + 6) % 7

function cardProps(facility) {
  const hours = hoursByVenue.value[facility.venue?.public_id] ?? []
  const today = hours.find((entry) => entry.day_of_week === todayIndex) ?? null
  return {
    title: facility.name,
    location: venueOf(facility)?.address ?? '',
    tags: tagsOf(facility),
    openTime: today?.is_closed ? 'Closed today' : (today?.opens_at ?? ''),
    closeTime: today?.is_closed ? '' : (today?.closes_at ?? ''),
  }
}

onMounted(async () => {
  loading.value = true
  await venuesStore.load()
  try {
    venues.value = await fetchVenues()
    const pairs = await Promise.all(
      venues.value.map(async (venue) => [venue.public_id, await fetchVenueHours(venue.public_id)]),
    )
    hoursByVenue.value = Object.fromEntries(pairs)
    error.value = ''
  } catch (err) {
    error.value = errorDetail(err, 'Could not load the venues.')
  } finally {
    loading.value = false
  }
})

// Keep a selection that is still on screen (bookable when there is one).
watch(
  visibleFacilities,
  (list) => {
    if (list.some((facility) => facility.public_id === selectedKey.value)) return
    const next = list.find((facility) => facility.is_bookable) ?? list[0]
    selectedKey.value = next?.public_id ?? ''
  },
  { immediate: true },
)

// A date nobody can book (no free hour) is greyed out on the calendar.
async function checkAvailability(facility) {
  selectedKey.value = facility.public_id
  if (!facility.is_bookable) {
    checkedKey.value = ''
    fullyBookedDates.value = []
    return
  }
  try {
    const from = toIsoDate(new Date())
    const to = toIsoDate(addDays(new Date(), 30))
    const days = await fetchAvailabilityDates(facility.public_id, from, to)
    fullyBookedDates.value = days.filter((day) => day.free_hours === 0).map((day) => day.day)
    checkedKey.value = facility.public_id
    error.value = ''
  } catch (err) {
    error.value = errorDetail(err, 'Could not load availability.')
    checkedKey.value = ''
    fullyBookedDates.value = []
  }
}

function goToBooking(date) {
  router.push({ name: 'booking', query: { date, facility: selectedKey.value } })
}
</script>

<template>
  <section class="space-y-4">
    <BookingCalendar
      :booked-dates="availabilityChecked ? fullyBookedDates : []"
      :bookable="availabilityChecked"
      @book="goToBooking"
    />
    <LocationPanel
      :filter-groups="filterGroups"
      :filters="filters"
      :venues="venues"
      @update:filters="filters = $event"
    />
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
    <p v-if="selected && !availabilityChecked" class="text-sm text-gray-600" role="status">
      {{ selected.name }} is selected. Check availability to see its free dates.
    </p>
    <div class="venue-grid">
      <VenueCard
        v-for="facility in visibleFacilities"
        :key="facility.public_id"
        v-bind="cardProps(facility)"
        @check-availability="checkAvailability(facility)"
      />
    </div>
    <p v-if="!visibleFacilities.length && !loading" class="text-sm text-gray-600">
      No venue matches those filters.
    </p>
  </section>
</template>
