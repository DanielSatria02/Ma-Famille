<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import BookingCalendar from '../components/BookingCalendar.vue'
import OccupancyChart from '../components/OccupancyChart.vue'
import StatsOverview from '../components/StatsOverview.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
import UnavailableNotice from '../components/UnavailableNotice.vue'
import UpcomingBookings from '../components/UpcomingBookings.vue'
import VenueStatus from '../components/VenueStatus.vue'
import { generateSlots, errorDetail, fetchVenueHours, updateVenueHours } from '../services/api.js'
import { useBookingsStore } from '../stores/bookings.js'
import { useVenuesStore } from '../stores/venues.js'
import { addDays, toIsoDate } from '../utils/date.js'
import '../styles/manager.css'

// Four things a venue manager does, not fourteen panels in one column.
//
// The dashboard used to be a single 7500px scroll: the day's visitors, the slot
// calendar, opening hours, per-facility hours, photos, pricing, promotions, the
// audit log and the venue switch, stacked in the order they were built, with no
// headings. "Generate slots for 30 days" — the button that decides whether
// anything is bookable at all — sat eleventh, below the fold, looking exactly
// like the rest.
//
// So the page is grouped by what the manager is trying to do. The day's work is
// on screen when the page opens; the settings live behind the tab that names
// them.

const TABS = [
  { id: 'day', label: 'Today' },
  { id: 'slots', label: 'Slots' },
  { id: 'venue', label: 'Venue' },
  { id: 'records', label: 'Records' },
]

const tab = ref('day')

// Each settings panel fetches on mount and owns a form. Loading all of them to
// show one costs a round trip per panel on every visit, so the ones that are
// not on screen are not built.
const LazyAuditTrail = defineAsyncComponent(() => import('../components/AuditTrail.vue'))
const LazyGuestMessages = defineAsyncComponent(() => import('../components/GuestMessages.vue'))
const LazyManageHours = defineAsyncComponent(() => import('../components/ManageHours.vue'))
const LazyOpeningSchedule = defineAsyncComponent(() => import('../components/OpeningSchedule.vue'))
const LazyPhotoSettings = defineAsyncComponent(() => import('../components/PhotoSettings.vue'))
const LazyPricingSettings = defineAsyncComponent(() => import('../components/PricingSettings.vue'))
const LazyPromoSettings = defineAsyncComponent(() => import('../components/PromoSettings.vue'))

const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const bookingsStore = useBookingsStore()
const { todaysBookings, upcomingBookings, bookedDates, weeklyVisitors, canceledCount: canceledBookings } =
  storeToRefs(bookingsStore)

const venuesStore = useVenuesStore()
const { venues, pricing, venueStatusItems } = storeToRefs(venuesStore)

const openingSchedule = ref([])
const notice = ref('')
const syncing = ref(false)
const venuesError = computed(() => venuesStore.error)

const activeVenue = computed(() => venuesStore.activeVenue)
const activeVenueId = computed(() => activeVenue.value?.venue?.public_id ?? '')

// A count on the tab, so "Today" is worth opening even when the list is empty and
// the manager has not looked yet.
const todayCount = computed(() => todaysBookings.value.length)

async function loadSchedule() {
  if (!activeVenueId.value) return
  const days = await fetchVenueHours(activeVenueId.value)
  openingSchedule.value = days.map((entry) => ({
    day: DAY_NAMES[entry.day_of_week] ?? entry.day,
    dayOfWeek: entry.day_of_week,
    start: entry.opens_at,
    end: entry.closes_at,
    isClosed: entry.is_closed,
  }))
}

onMounted(async () => {
  await venuesStore.loadForManager()
  await bookingsStore.load({
    fromDay: toIsoDate(new Date()),
    toDay: toIsoDate(addDays(new Date(), 7)),
  })
  try {
    notice.value = ''
    await loadSchedule()
  } catch (err) {
    notice.value = errorDetail(err, 'Could not load the opening schedule.')
  }
})

function cancelBooking(booking) {
  bookingsStore.cancelBooking(booking.id)
}

function confirmVisit(booking) {
  bookingsStore.confirmVisit(booking.id)
}

function markVisitPaid(booking) {
  bookingsStore.markVisitPaid(booking.id)
}

function refundVisit(booking) {
  bookingsStore.refundVisit(booking.id)
}

async function updateSchedule({ day, start, end }) {
  const entry = openingSchedule.value.find((item) => item.day === day)
  if (!entry || !activeVenueId.value) return
  try {
    await updateVenueHours(activeVenueId.value, entry.dayOfWeek, {
      opensAt: start,
      closesAt: end,
      isClosed: false,
    })
    Object.assign(entry, { start, end, isClosed: false })
    notice.value = 'Opening hours saved. Generate slots so clients can book them.'
  } catch (err) {
    notice.value = errorDetail(err, 'Could not save the opening hours.')
  }
}

// Hours only become bookable once slots exist for them. It is here, on the tab
// about slots, rather than below six other panels.
async function generateMonth() {
  if (syncing.value) return
  syncing.value = true
  notice.value = ''
  try {
    const from = toIsoDate(new Date())
    const to = toIsoDate(addDays(new Date(), 30))
    const results = []
    for (const facility of venuesStore.facilities) {
      if (!facility.is_bookable) continue
      results.push(
        await generateSlots({ courtPublicId: facility.public_id, fromDay: from, toDay: to }),
      )
    }
    const created = results.reduce((sum, result) => sum + result.created, 0)
    const unpriced = results.reduce((sum, result) => sum + (result.skipped_unpriced ?? 0), 0)
    notice.value = `Generated ${created} slot(s) for the next 30 days.`
    if (unpriced) notice.value += ` ${unpriced} facility-day(s) skipped: no price set.`
    await bookingsStore.load({
      fromDay: from,
      toDay: toIsoDate(addDays(new Date(), 7)),
    })
  } catch (err) {
    notice.value = errorDetail(err, 'Could not generate the slots.')
  } finally {
    syncing.value = false
  }
}
</script>

<template>
  <div class="manager">
    <h1 class="manager-title">Dashboard</h1>

    <p v-if="venuesError" class="text-sm text-red-600" role="alert">{{ venuesError }}</p>
    <p v-if="bookingsStore.error" class="text-sm text-red-600" role="alert">{{ bookingsStore.error }}</p>
    <p v-if="notice" class="manager-notice" role="status">{{ notice }}</p>
    <p v-if="bookingsStore.notice" class="manager-notice" role="status">
      {{ bookingsStore.notice }}
    </p>

    <nav class="manager-tabs" role="tablist" aria-label="Dashboard sections">
      <button
        v-for="option in TABS"
        :key="option.id"
        type="button"
        role="tab"
        class="manager-tab"
        :class="{ 'is-active': tab === option.id }"
        :aria-selected="tab === option.id"
        @click="tab = option.id"
      >
        {{ option.label }}
        <span v-if="option.id === 'day' && todayCount" class="manager-tab-count">{{ todayCount }}</span>
      </button>
    </nav>

    <!--
      The day's work. Confirming a visitor, taking payment and cancelling are
      the things a manager opens the dashboard to do, so they are what is on
      screen when it loads.
    -->
    <section v-if="tab === 'day'" class="manager-panels" role="tabpanel">
      <UnavailableNotice :venues="venues" />
      <StatsOverview
        :weekly-visitors="weeklyVisitors"
        :todays-bookings="todaysBookings.length"
        :canceled-bookings="canceledBookings"
      />
      <TodaysVisitors
        :bookings="todaysBookings"
        @confirm="confirmVisit"
        @mark-paid="markVisitPaid"
        @refund="refundVisit"
      />
      <UpcomingBookings
        :bookings="upcomingBookings"
        @cancel="cancelBooking"
        @confirm="confirmVisit"
        @mark-paid="markVisitPaid"
        @refund="refundVisit"
      />
      <!-- The backend pages at 50; say how much of the window is on screen so a
           busy day is never mistaken for a quiet one. -->
      <div
        v-if="bookingsStore.totalBookings > 0"
        class="flex items-center justify-between gap-3 text-sm text-gray-600"
      >
        <span role="status">
          Showing {{ bookingsStore.bookings.length }} of {{ bookingsStore.totalBookings }} booked
          hours
        </span>
        <button
          v-if="bookingsStore.hasMore"
          type="button"
          class="manager-more"
          :disabled="bookingsStore.loading"
          @click="bookingsStore.loadMore"
        >
          {{ bookingsStore.loading ? 'Loading…' : 'Load more' }}
        </button>
      </div>
    </section>

    <!-- What is bookable, and opening the book. -->
    <section v-else-if="tab === 'slots'" class="manager-panels" role="tabpanel">
      <div class="manager-action">
        <p class="manager-action-text">
          Slots are what clients actually book. Until they exist for a day, that day cannot be
          chosen, however the opening hours are set.
        </p>
        <button type="button" class="manager-primary" :disabled="syncing" @click="generateMonth">
          {{ syncing ? 'Generating…' : 'Generate slots for 30 days' }}
        </button>
      </div>
      <BookingCalendar allow-past-months :booked-dates="bookedDates" />
      <OccupancyChart />
    </section>

    <!-- How the venue is set up. -->
    <section v-else-if="tab === 'venue'" class="manager-panels" role="tabpanel">
      <LazyOpeningSchedule :schedule="openingSchedule" @update="updateSchedule" />
      <LazyManageHours
        :facilities="venuesStore.facilities"
        :venue-public-id="activeVenueId"
      />
      <LazyPricingSettings :items="pricing" @update="venuesStore.updatePricing" />
      <LazyPromoSettings />
      <LazyPhotoSettings :facilities="venuesStore.facilities" :venue-public-id="activeVenueId" />
      <VenueStatus :venues="venueStatusItems" @toggle="venuesStore.toggleVenue" />
    </section>

    <!-- Messages and who changed what. -->
    <section v-else class="manager-panels" role="tabpanel">
      <LazyGuestMessages />
      <LazyAuditTrail />
    </section>
  </div>
</template>