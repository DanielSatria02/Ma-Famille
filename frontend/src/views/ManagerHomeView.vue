<script setup>
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import BookingCalendar from '../components/BookingCalendar.vue'
import GuestMessages from '../components/GuestMessages.vue'
import ManageHours from '../components/ManageHours.vue'
import OccupancyChart from '../components/OccupancyChart.vue'
import OpeningSchedule from '../components/OpeningSchedule.vue'
import PhotoSettings from '../components/PhotoSettings.vue'
import PricingSettings from '../components/PricingSettings.vue'
import PromoSettings from '../components/PromoSettings.vue'
import StatsOverview from '../components/StatsOverview.vue'
import TodaysVisitors from '../components/TodaysVisitors.vue'
import UnavailableNotice from '../components/UnavailableNotice.vue'
import UpcomingBookings from '../components/UpcomingBookings.vue'
import VenueStatus from '../components/VenueStatus.vue'
import { generateSlots, errorDetail, fetchVenueHours, updateVenueHours } from '../services/api.js'
import { useBookingsStore } from '../stores/bookings.js'
import { useVenuesStore } from '../stores/venues.js'
import { addDays, toIsoDate } from '../utils/date.js'

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

// Hours only become bookable once slots exist for them.
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
  <section class="space-y-4">
    <StatsOverview
      :weekly-visitors="weeklyVisitors"
      :todays-bookings="todaysBookings.length"
      :canceled-bookings="canceledBookings"
    />
    <p v-if="venuesError" class="text-sm text-red-600" role="alert">{{ venuesError }}</p>
    <p v-if="bookingsStore.error" class="text-sm text-red-600" role="alert">{{ bookingsStore.error }}</p>
    <p v-if="bookingsStore.notice" class="text-sm text-gray-600" role="status">
      {{ bookingsStore.notice }}
    </p>
    <UnavailableNotice :venues="venues" />
    <BookingCalendar allow-past-months :booked-dates="bookedDates" />
    <OccupancyChart />
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
    <p v-if="notice" class="text-sm text-gray-600" role="status">{{ notice }}</p>
    <button
      type="button"
      class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50"
      :disabled="syncing"
      @click="generateMonth"
    >
      Generate slots for 30 days
    </button>
    <OpeningSchedule :schedule="openingSchedule" @update="updateSchedule" />
    <ManageHours :facilities="venuesStore.facilities" :venue-public-id="activeVenueId" />
    <PhotoSettings :facilities="venuesStore.facilities" :venue-public-id="activeVenueId" />
    <GuestMessages />
    <PricingSettings :items="pricing" @update="venuesStore.updatePricing" />
    <PromoSettings />
    <VenueStatus :venues="venueStatusItems" @toggle="venuesStore.toggleVenue" />
  </section>
</template>
