<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  blockSlots,
  createVenueClosure,
  deleteVenueClosure,
  errorDetail,
  fetchDayAvailability,
  fetchVenueClosures,
} from '../services/api.js'
import { addDays, formatLongDate, formatHour, toIsoDate } from '../utils/date.js'
import '../styles/manage-hours.css'

const props = defineProps({
  facilities: { type: Array, default: () => [] },
  venuePublicId: { type: String, default: '' },
})

const HOURS = Array.from({ length: 24 }, (_, hour) => hour)

const today = toIsoDate(new Date())
const facilityId = ref('')
const day = ref(today)
const dayState = ref(null)
const closures = ref([])
const fromHour = ref(9)
const toHour = ref(11)
const closureFrom = ref(today)
const closureTo = ref(toIsoDate(addDays(new Date(), 1)))
const closureReason = ref('')
const note = ref('')
const error = ref('')
const busy = ref(false)

const bookable = computed(() => props.facilities.filter((item) => item.is_bookable))
const isClosed = computed(() => dayState.value?.is_closed ?? false)
const busyHours = computed(
  () => (dayState.value?.hours ?? []).filter((entry) => entry.status !== 'available').length,
)
const canClose = computed(() => !isClosed.value && busyHours.value > 0)

watch(
  () => props.facilities,
  (items) => {
    if (!facilityId.value && items.length) facilityId.value = items.find((i) => i.is_bookable)?.public_id ?? ''
  },
  { immediate: true },
)

async function loadDay() {
  if (!facilityId.value) return
  error.value = ''
  try {
    dayState.value = await fetchDayAvailability(facilityId.value, day.value)
  } catch (err) {
    dayState.value = null
    error.value = errorDetail(err, 'Could not load the hours of that day.')
  }
}

async function loadClosures() {
  if (!props.venuePublicId) return
  try {
    closures.value = await fetchVenueClosures(props.venuePublicId)
  } catch (err) {
    error.value = errorDetail(err, 'Could not load the closure dates.')
  }
}

// One call closes (or reopens) a whole window; the reply says what it skipped.
async function applyWindow(status) {
  if (!facilityId.value) return
  busy.value = true
  note.value = ''
  error.value = ''
  try {
    const result = await blockSlots({
      facilityPublicId: facilityId.value,
      fromDay: day.value,
      toDay: day.value,
      fromHour: fromHour.value,
      toHour: toHour.value,
      status,
    })
    const verb = status === 'blocked' ? 'Closed' : 'Reopened'
    note.value = `${verb} ${result.updated} hour(s).`
    if (result.skipped_booked) {
      note.value += ` ${result.skipped_booked} hour(s) left alone: already booked.`
    }
    if (result.unchanged) note.value += ` ${result.unchanged} already in that state.`
    if (result.skipped_missing) {
      note.value += ` ${result.skipped_missing} hour(s) have no slot row (generate first).`
    }
    await loadDay()
  } catch (err) {
    error.value = errorDetail(err, 'Could not change those hours.')
  } finally {
    busy.value = false
  }
}

async function addClosure() {
  if (!props.venuePublicId) {
    error.value = 'Pick a venue first.'
    return
  }
  busy.value = true
  note.value = ''
  error.value = ''
  try {
    const created = await createVenueClosure(props.venuePublicId, {
      startsOn: closureFrom.value,
      endsOn: closureTo.value,
      reason: closureReason.value.trim(),
    })
    note.value = `Club closed for ${created.days} day(s).`
    if (created.affected_bookings) {
      note.value += ` Careful: ${created.affected_bookings} booking(s) fall inside it.`
    }
    closureReason.value = ''
    await Promise.all([loadClosures(), loadDay()])
  } catch (err) {
    error.value = errorDetail(err, 'Could not close those dates.')
  } finally {
    busy.value = false
  }
}

async function removeClosure(closure) {
  busy.value = true
  note.value = ''
  error.value = ''
  try {
    await deleteVenueClosure(props.venuePublicId, closure.public_id)
    note.value = 'Dates reopened.'
    await Promise.all([loadClosures(), loadDay()])
  } catch (err) {
    error.value = errorDetail(err, 'Could not reopen those dates.')
  } finally {
    busy.value = false
  }
}

function statusClass(status) {
  return `hour-cell is-${status}`
}

onMounted(async () => {
  await loadDay()
  await loadClosures()
})

watch([facilityId, day], loadDay)
watch(() => props.venuePublicId, loadClosures)
</script>

<template>
  <section class="manage-hours" aria-labelledby="manage-hours-title">
    <h2 id="manage-hours-title" class="manage-hours-title">Manage Hours</h2>

    <div class="manage-row">
      <label class="manage-field">
        <span>Facility</span>
        <select v-model="facilityId">
          <option v-for="item in bookable" :key="item.public_id" :value="item.public_id">
            {{ item.name }}
          </option>
        </select>
      </label>
      <label class="manage-field">
        <span>Day</span>
        <input v-model="day" type="date" />
      </label>
    </div>

    <p v-if="dayState" class="manage-line">
      {{ formatLongDate(day) }} —
      <template v-if="isClosed">
        closed<template v-if="dayState.closure_reason"> ({{ dayState.closure_reason }})</template>
      </template>
      <template v-else>
        bookable {{ dayState.opens_at }} - {{ dayState.closes_at }}, {{ busyHours }} hour(s) taken
      </template>
    </p>

    <ul v-if="dayState && !isClosed" class="hour-grid">
      <li v-for="entry in dayState.hours" :key="entry.hour" :class="statusClass(entry.status)">
        <span class="hour-label">{{ formatHour(entry.hour) }}</span>
        <span class="hour-status">{{ entry.status }}</span>
      </li>
    </ul>

    <div class="manage-row">
      <label class="manage-field">
        <span>From</span>
        <select v-model.number="fromHour">
          <option v-for="hour in HOURS" :key="hour" :value="hour">{{ formatHour(hour) }}</option>
        </select>
      </label>
      <label class="manage-field">
        <span>To</span>
        <select v-model.number="toHour">
          <option v-for="hour in HOURS.slice(1)" :key="hour" :value="hour">{{ formatHour(hour) }}</option>
        </select>
      </label>
      <button type="button" class="manage-button" :disabled="busy || !canClose" @click="applyWindow('blocked')">
        Close hours
      </button>
      <button
        type="button"
        class="manage-button"
        :disabled="busy || !facilityId"
        @click="applyWindow('available')"
      >
        Reopen hours
      </button>
    </div>

    <h3 class="manage-subtitle">Closure dates</h3>
    <ul v-if="closures.length" class="closure-list">
      <li v-for="closure in closures" :key="closure.public_id" class="closure-item">
        <span>
          {{ formatLongDate(closure.starts_on) }} - {{ formatLongDate(closure.ends_on) }}
          ({{ closure.days }} day(s))<template v-if="closure.reason"> · {{ closure.reason }}</template>
        </span>
        <button type="button" class="manage-button" :disabled="busy" @click="removeClosure(closure)">
          Reopen
        </button>
      </li>
    </ul>
    <p v-else class="manage-line">No closed dates.</p>

    <div class="manage-row">
      <label class="manage-field">
        <span>Close from</span>
        <input v-model="closureFrom" type="date" />
      </label>
      <label class="manage-field">
        <span>until</span>
        <input v-model="closureTo" type="date" />
      </label>
      <label class="manage-field manage-field-wide">
        <span>Reason</span>
        <input v-model="closureReason" type="text" maxlength="120" placeholder="Renovation" />
      </label>
      <button type="button" class="manage-button" :disabled="busy" @click="addClosure">
        Close dates
      </button>
    </div>

    <p v-if="note" class="text-sm text-gray-600" role="status">{{ note }}</p>
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
  </section>
</template>
