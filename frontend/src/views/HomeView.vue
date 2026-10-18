<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BookingCalendar from '../components/BookingCalendar.vue'
import ReviewsPanel from '../components/ReviewsPanel.vue'
import VenueCard from '../components/VenueCard.vue'
import { errorDetail, fetchAvailabilityDates, fetchVenueHours, fetchVenues } from '../services/api.js'
import { useVenuesStore } from '../stores/venues.js'
import { addDays, formatLongDate, toIsoDate } from '../utils/date.js'
import { minBookableDate } from '../utils/bookingRules.js'
import { hasCoordinates } from '../utils/maps.js'
import { resolveImage } from '../utils/image.js'

// The map pulls in Leaflet, which is worth 145KB of JavaScript. Loading it here keeps
// it out of the first screenful, where the venue grid is what matters.
const LazyVenueMap = defineAsyncComponent(() => import('../components/VenueMap.vue'))

// One page, three decisions, in the order they get made.
//
// This used to open on a calendar that could do nothing yet, then a map, then
// a row of venue cards each with a "Check availability" button that only
// fetched a date list without letting you book it. Choosing a venue took four
// separate actions and ended in a second page where the venue had to be picked
// again. So: pick a venue, pick a day on the calendar that just appeared, go
// book.

const KIND_LABELS = { court: 'Court', office: 'Private Office', cafe: 'Cafe' }

const router = useRouter()
const venuesStore = useVenuesStore()

const venues = ref([])
const hoursByVenue = ref({})
const filters = ref({ kind: [], tag: [] })
const selectedKey = ref('')
const checkedKey = ref('')
const fullyBookedDates = ref([])
const loading = ref(false)
const error = ref('')
// Dates the server said have at least one free hour. Empty until the venue is
// chosen, and shown as "not checked yet" rather than as "no free dates".
const checkedDates = ref([])

const facilities = computed(() => venuesStore.facilities)
const venueOf = (facility) =>
  venues.value.find((venue) => venue.public_id === facility?.venue?.public_id) ?? null
const tagsOf = (facility) => venueOf(facility)?.tags ?? []

const selected = computed(
  () => facilities.value.find((facility) => facility.public_id === selectedKey.value) ?? null,
)
const selectedVenue = computed(() => venueOf(selected.value))
const availabilityChecked = computed(
  () => Boolean(checkedKey.value) && checkedKey.value === selectedKey.value,
)

// The map is per venue, not per facility: a venue with three courts has one
// address and one pin, and three markers on the same spot would be noise. The
// venues without coordinates are dropped, and the map says so rather than
// showing an empty grey box.
const mapVenues = computed(() => venues.value.filter(hasCoordinates))
const activeVenueOnMap = computed(() => selectedVenue.value?.public_id ?? '')

// Only the kinds and tags actually in use are offered as filters.
const filterGroups = computed(() => {
  const kinds = [...new Set(facilities.value.map((facility) => facility.kind))]
  const tags = [...new Set(venues.value.flatMap((venue) => venue.tags ?? []))].sort()
  const groups = []
  if (kinds.length) {
    groups.push({
      key: 'kind',
      title: 'Type',
      options: kinds.map((kind) => ({ value: kind, label: KIND_LABELS[kind] ?? kind })),
    })
  }
  if (tags.length) {
    groups.push({
      key: 'tag',
      title: 'Area',
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
    image: resolveImage(facility.image_url),
    isChosen: facility.public_id === selectedKey.value,
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

// Tapping a pin selects that venue's first bookable facility, which is what the
// visitor would have clicked on the card grid directly below. Selecting the
// venue rather than jumping straight to a facility matters when the venue has
// several and only some of them are bookable: the first bookable one is the one
// the grid would have chosen for them anyway.
function selectVenueOnMap(venuePublicId) {
  const candidates = facilities.value.filter(
    (facility) => facility.venue?.public_id === venuePublicId,
  )
  const target = candidates.find((facility) => facility.is_bookable) ?? candidates[0]
  if (target) selectedKey.value = target.public_id
}

// Picking a venue loads its calendar straight away. The old flow made this a
// separate button, so the visitor had to know that clicking a card was not
// selecting it.
watch(selectedKey, async (key) => {
  if (!key || key === checkedKey.value) return
  const facility = facilities.value.find((entry) => entry.public_id === key)
  if (!facility?.is_bookable) {
    checkedKey.value = ''
    checkedDates.value = []
    return
  }
  try {
    const from = toIsoDate(new Date())
    const to = toIsoDate(addDays(new Date(), 30))
    const days = await fetchAvailabilityDates(key, from, to)
    checkedDates.value = days
    fullyBookedDates.value = days.filter((day) => day.free_hours === 0).map((day) => day.day)
    checkedKey.value = key
    error.value = ''
  } catch (err) {
    error.value = errorDetail(err, 'Could not load availability.')
    checkedKey.value = ''
    checkedDates.value = []
  }
})

// The soonest day that can actually be booked. Bookings are a day ahead, so a
// date with free hours today is not an option: sending the visitor there would
// land them on a form that quietly refuses the date, which reads as the page
// having lost what they picked. Computed from the same rule the form uses, so
// the link and the form always agree.
const nextOpenDay = computed(() => {
  if (!availabilityChecked.value) return ''
  const earliest = minBookableDate()
  const free = checkedDates.value.find((day) => day.free_hours > 0 && day.day >= earliest)
  return free?.day ?? ''
})

function goToBooking(date) {
  router.push({ name: 'booking', query: { date, facility: selectedKey.value } })
}

// A number nobody has to add up themselves.
const freeHoursTotal = computed(() =>
  checkedDates.value.reduce((sum, day) => sum + day.free_hours, 0),
)
</script>

<template>
  <div class="home">
    <!--
      A visitor's first question is "what can I book here", so the venues come
      first. The map and the filters are tools for that question, so they sit
      with them rather than above them.
    -->
    <section class="home-step" aria-labelledby="home-step-venue">
      <header class="home-step-head">
        <p class="home-step-number">1</p>
        <div>
          <h1 id="home-step-venue" class="home-step-title">Pick a place</h1>
          <p class="home-step-hint">
            {{ visibleFacilities.length }}
            {{ visibleFacilities.length === 1 ? 'court' : 'courts' }} open for booking
          </p>
        </div>
      </header>

      <div class="home-filters">
        <label v-for="group in filterGroups" :key="group.key" class="home-filter">
          <span class="home-filter-label">{{ group.title }}</span>
          <select
            class="home-filter-select"
            :value="filters[group.key]?.[0] ?? ''"
            @change="
              filters[group.key] = $event.target.value
                ? [$event.target.value]
                : []
            "
          >
            <option value="">All</option>
            <option v-for="option in group.options" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
      </div>

      <div class="venue-grid">
        <VenueCard
          v-for="(facility, index) in visibleFacilities"
          :key="facility.public_id"
          v-bind="cardProps(facility)"
          class="stagger-item"
          :style="{ animationDelay: `${Math.min(index, 8) * 40}ms` }"
          @select="selectedKey = facility.public_id"
        />
      </div>
      <p v-if="!visibleFacilities.length && !loading" class="text-sm text-gray-600">
        No venue matches those filters.
      </p>

      <!-- Below the grid, not above it: someone opening the front page is
           asking what they can book here, and only once they know what it is
           does the street address matter. -->
      <LazyVenueMap
        :venues="mapVenues"
        :active-public-id="activeVenueOnMap"
        @select="selectVenueOnMap"
      />
    </section>

    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>

    <!--
      Step 2 only appears once there is something to pick a day for. A calendar
      that sits at the top of the page before a venue is chosen looks like the
      main control of the page and does nothing.
    -->
    <section v-if="selected" class="home-step" aria-labelledby="home-step-date">
      <header class="home-step-head">
        <p class="home-step-number">2</p>
        <div>
          <h2 id="home-step-date" class="home-step-title">Pick a day</h2>
          <p class="home-step-hint">
            <template v-if="!selected.is_bookable">
              {{ selected.name }} is not taking bookings right now.
            </template>
            <template v-else-if="availabilityChecked">
              {{ selected.name }} has
              {{ freeHoursTotal }} free hours in the next month.
              <button
                v-if="nextOpenDay"
                type="button"
                class="home-jump"
                @click="goToBooking(nextOpenDay)"
              >
                Book {{ formatLongDate(nextOpenDay) }}
              </button>
            </template>
            <template v-else>Checking {{ selected.name }}...</template>
          </p>
        </div>
      </header>

      <BookingCalendar
        v-if="selected.is_bookable && availabilityChecked"
        :booked-dates="fullyBookedDates"
        :min-date="minBookableDate()"
        :initial-date="nextOpenDay"
        bookable
        @book="goToBooking"
      />
    </section>

    <ReviewsPanel
      v-if="selectedVenue"
      :key="selectedVenue.public_id"
      :venue-public-id="selectedVenue.public_id"
      :venue-name="selectedVenue.name"
    />
  </div>
</template>
