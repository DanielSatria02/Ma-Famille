<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BookingCalendar from '../components/BookingCalendar.vue'
import ReviewsPanel from '../components/ReviewsPanel.vue'
import VenueCard from '../components/VenueCard.vue'
import {
  errorDetail,
  fetchVenueAvailabilityDates,
  fetchVenueHours,
  fetchVenues,
} from '../services/api.js'
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

const router = useRouter()
const venuesStore = useVenuesStore()

const venues = ref([])
const hoursByVenue = ref({})
const filters = ref({ tag: [] })
const selectedKey = ref('')
const checkedKey = ref('')
const fullyBookedDates = ref([])
const loading = ref(false)
const error = ref('')
// Dates the server said have at least one free hour. Empty until the club is
// chosen, and shown as "not checked yet" rather than as "no free dates".
const checkedDates = ref([])

const facilities = computed(() => venuesStore.facilities)
const venueOf = (facility) =>
  venues.value.find((venue) => venue.public_id === facility?.venue?.public_id) ?? null
const tagsOf = (venue) => venue?.tags ?? []

// The clubs, each with the courts inside it. One card per club: a visitor
// chooses where to play, and which of its courts they get is the second
// question, not the first. Listing every court made the grid four times
// longer than the number of places, and repeated the same address on each
// row.
const clubs = computed(() =>
  venues.value.map((venue) => {
    const courts = facilities.value.filter(
      (facility) => facility.venue?.public_id === venue.public_id,
    )
    return {
      venue,
      courts,
      courtCount: courts.length,
      openCourts: courts.filter((court) => court.is_bookable).length,
      // The cheapest rate in the club, so the card can say what it starts at.
      fromPrice: courts
        .map((court) => court.price_weekday ?? 0)
        .filter((price) => price > 0)
        .sort((a, b) => a - b)[0] ?? 0,
    }
  }),
)

const selectedClub = computed(
  () => clubs.value.find((club) => club.venue.public_id === selectedKey.value) ?? null,
)
const selectedVenue = computed(() => selectedClub.value?.venue ?? null)
const availabilityChecked = computed(
  () => Boolean(checkedKey.value) && checkedKey.value === selectedKey.value,
)

// The map is per venue, not per facility: a venue with three courts has one
// address and one pin, and three markers on the same spot would be noise. The
// venues without coordinates are dropped, and the map says so rather than
// showing an empty grey box.
const mapVenues = computed(() => venues.value.filter(hasCoordinates))
const activeVenueOnMap = computed(() => selectedVenue.value?.public_id ?? '')

// Only the tags actually in use are offered as filters. The kind of a court
// is not one of them: every court here is a padel court, so a filter on it
// would offer one option and hide nothing.
const filterGroups = computed(() => {
  const tags = [...new Set(venues.value.flatMap((venue) => venue.tags ?? []))].sort()
  if (!tags.length) return []
  return [
    {
      key: 'tag',
      title: 'Area',
      options: tags.map((tag) => ({ value: tag, label: tag })),
    },
  ]
})

const visibleClubs = computed(() =>
  clubs.value.filter((club) => {
    const tags = filters.value.tag ?? []
    if (tags.length && !tags.some((tag) => club.venue.tags?.includes(tag))) return false
    return true
  }),
)

// Monday-first index, like the backend's day_of_week.
const todayIndex = (new Date().getDay() + 6) % 7

function cardProps(club) {
  const hours = hoursByVenue.value[club.venue.public_id] ?? []
  const today = hours.find((entry) => entry.day_of_week === todayIndex) ?? null
  return {
    title: club.venue.name,
    location: club.venue.address ?? '',
    tags: tagsOf(club.venue),
    openTime: today?.is_closed ? 'Closed today' : (today?.opens_at ?? ''),
    closeTime: today?.is_closed ? '' : (today?.closes_at ?? ''),
    courts: club.courtCount,
    fromPrice: club.fromPrice,
    image: resolveImage(club.venue.image_url),
    isChosen: club.venue.public_id === selectedKey.value,
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
  visibleClubs,
  (list) => {
    if (list.some((club) => club.venue.public_id === selectedKey.value)) return
    const next = list.find((club) => club.openCourts > 0) ?? list[0]
    selectedKey.value = next?.venue.public_id ?? ''
  },
  { immediate: true },
)

// Tapping a pin selects that club, which is what the visitor would have
// clicked on the card grid directly below.
function selectVenueOnMap(venuePublicId) {
  if (visibleClubs.value.some((club) => club.venue.public_id === venuePublicId)) {
    selectedKey.value = venuePublicId
  }
}

// Picking a venue loads its calendar straight away. The old flow made this a
// separate button, so the visitor had to know that clicking a card was not
// selecting it.
watch(selectedKey, async (key) => {
  if (!key || key === checkedKey.value) return
  const club = clubs.value.find((entry) => entry.venue.public_id === key)
  if (!club || club.openCourts === 0) {
    checkedKey.value = ''
    checkedDates.value = []
    return
  }
  try {
    const from = toIsoDate(new Date())
    const to = toIsoDate(addDays(new Date(), 30))
    // The club, not one of its courts: the visitor picked the club, so the
    // hours they are shown are the club's.
    const days = await fetchVenueAvailabilityDates(key, from, to)
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

// The booking form needs a court, and the visitor picked a club. The first
// bookable court of that club is the one the grid would have chosen for them.
function firstBookableCourt(club) {
  if (!club) return ''
  const target = club.courts.find((court) => court.is_bookable) ?? club.courts[0]
  return target?.public_id ?? ''
}

function goToBooking(date) {
  const court = firstBookableCourt(selectedClub.value)
  if (!court) return
  router.push({ name: 'booking', query: { date, facility: court } })
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
          <h1 id="home-step-venue" class="home-step-title">Pick a club</h1>
          <p class="home-step-hint">
            {{ visibleClubs.length }}
            {{ visibleClubs.length === 1 ? 'club' : 'clubs' }} open for booking
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
          v-for="(club, index) in visibleClubs"
          :key="club.venue.public_id"
          v-bind="cardProps(club)"
          class="stagger-item"
          :style="{ animationDelay: `${Math.min(index, 8) * 40}ms` }"
          @select="selectedKey = club.venue.public_id"
        />
      </div>
      <p v-if="!visibleClubs.length && !loading" class="text-sm text-gray-600">
        No club matches those filters.
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
    <section v-if="selectedClub" class="home-step" aria-labelledby="home-step-date">
      <header class="home-step-head">
        <p class="home-step-number">2</p>
        <div>
          <h2 id="home-step-date" class="home-step-title">Pick a day</h2>
          <p class="home-step-hint">
            <template v-if="selectedClub.openCourts === 0">
              {{ selectedClub.venue.name }} is not taking bookings right now.
            </template>
            <template v-else-if="availabilityChecked">
              {{ selectedClub.venue.name }} has
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
            <template v-else>Checking {{ selectedClub.venue.name }}...</template>
          </p>
        </div>
      </header>

      <BookingCalendar
        v-if="selectedClub.openCourts > 0 && availabilityChecked"
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
