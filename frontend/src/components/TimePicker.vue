<script setup>
import { computed, ref, watch } from 'vue'
import PickerField from './PickerField.vue'
import { hasConflict } from '../utils/bookingRules.js'
import { formatHour } from '../utils/date.js'

// taken: Set of hours (0-23) already booked by other clients for the chosen facility and date.
// Time is chosen in whole hours only.
const props = defineProps({
  startHour: { type: Number, default: null },
  endHour: { type: Number, default: null },
  taken: { type: Object, default: () => new Set() },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['apply', 'toggle', 'close'])

// The hours are a grid of targets, not two dropdowns. A <select> of 23 hours is
// fine with a mouse and unusable on a phone: it opens a full-screen list, and
// the handful of hours that are actually free are scattered through it between
// disabled entries that all say "(booked)". Booking an hour nearby became four
// taps through a list of twenty-three.
//
// Now the first tap sets the start, the second ends the range there. Free hours
// are plain targets; taken ones are dimmed and untappable, so the grid itself
// shows what is left.
const HOURS = Array.from({ length: 23 }, (_, hour) => hour)

const draftStart = ref(props.startHour ?? null)
const error = ref('')

// Keep the draft in step when the parent changes or clears the time.
watch(
  () => [props.startHour, props.endHour],
  ([start]) => {
    draftStart.value = start ?? null
    error.value = ''
  },
)

const label = computed(() =>
  props.startHour === null ? '' : `${formatHour(props.startHour)} - ${formatHour(props.endHour)}`,
)

function pick(hour) {
  if (props.taken.has(hour)) return
  const start = draftStart.value
  // First tap, or a tap at or before the start: that is a new start.
  if (start === null || hour <= start) {
    draftStart.value = hour
    error.value = ''
    return
  }
  if (hasConflict(props.taken, start, hour)) {
    error.value = 'One of those hours is taken. Try a shorter run.'
    return
  }
  emit('apply', { start, end: hour })
  emit('close')
}

function startOver() {
  draftStart.value = null
  error.value = ''
}
</script>

<template>
  <PickerField label="Time" :value="label" :open="open" panel-class="is-time" @toggle="emit('toggle')">
    <div class="time-grid">
      <button
        v-for="hour in HOURS"
        :key="hour"
        type="button"
        class="time-chip"
        :class="{
          'is-taken': taken.has(hour),
          'is-start': draftStart === hour,
          'is-open':
            draftStart !== null && hour > draftStart && !hasConflict(taken, draftStart, hour),
        }"
        :disabled="taken.has(hour)"
        :aria-pressed="draftStart === hour"
        @click="pick(hour)"
      >
        {{ formatHour(hour) }}
      </button>
    </div>

    <p class="picker-hint" role="status">
      <template v-if="draftStart === null">Tap the hour you want to start.</template>
      <template v-else>Starting {{ formatHour(draftStart) }}. Tap the hour it ends.</template>
    </p>

    <p v-if="error" class="booking-error" role="alert">{{ error }}</p>

    <button v-if="draftStart !== null" type="button" class="picker-apply" @click="startOver">
      Pick a different start
    </button>
  </PickerField>
</template>