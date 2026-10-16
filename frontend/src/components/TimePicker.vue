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

const startOptions = Array.from({ length: 23 }, (_, hour) => hour)
const draftStart = ref(props.startHour ?? '')
const draftEnd = ref(props.endHour ?? '')
const error = ref('')

// Keep the drafts in step when the parent changes or clears the time.
watch(
  () => [props.startHour, props.endHour],
  ([start, end]) => {
    draftStart.value = start ?? ''
    draftEnd.value = end ?? ''
    error.value = ''
  },
)

const endOptions = computed(() => {
  const start = draftStart.value === '' ? 0 : draftStart.value
  return Array.from({ length: 24 - start - 1 }, (_, index) => start + 1 + index)
})

const label = computed(() =>
  props.startHour === null ? '' : `${formatHour(props.startHour)} - ${formatHour(props.endHour)}`,
)

const isComplete = computed(() => draftStart.value !== '' && draftEnd.value !== '')
const conflicts = computed(() => isComplete.value && hasConflict(props.taken, draftStart.value, draftEnd.value))

function onStartChange() {
  error.value = ''
  if (draftEnd.value !== '' && draftEnd.value <= draftStart.value) draftEnd.value = ''
}

function apply() {
  if (!isComplete.value) return
  if (conflicts.value) {
    error.value = 'That time is unavailable.'
    return
  }
  emit('apply', { start: draftStart.value, end: draftEnd.value })
  emit('close')
}
</script>

<template>
  <PickerField label="Time" :value="label" :open="open" panel-class="is-time" @toggle="emit('toggle')">
    <form class="time-form" @submit.prevent="apply">
      <div class="time-row">
        <label class="time-field">
          <span class="time-label">Start</span>
          <select v-model="draftStart" class="time-select" @change="onStartChange">
            <option value="" disabled>--:--</option>
            <option v-for="hour in startOptions" :key="hour" :value="hour" :disabled="taken.has(hour)">
              {{ formatHour(hour) }}{{ taken.has(hour) ? ' (booked)' : '' }}
            </option>
          </select>
        </label>
        <label class="time-field">
          <span class="time-label">End</span>
          <select v-model="draftEnd" class="time-select" :disabled="draftStart === ''" @change="error = ''">
            <option value="" disabled>--:--</option>
            <option v-for="hour in endOptions" :key="hour" :value="hour" :disabled="hasConflict(taken, draftStart, hour)">
              {{ formatHour(hour) }}{{ hasConflict(taken, draftStart, hour) ? ' (booked)' : '' }}
            </option>
          </select>
        </label>
      </div>

      <p v-if="error || conflicts" class="booking-error" role="alert">That time is unavailable.</p>

      <button type="submit" class="picker-apply" :disabled="!isComplete">Apply</button>
    </form>
  </PickerField>
</template>
