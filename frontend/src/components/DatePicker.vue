<script setup>
import BookingCalendar from './BookingCalendar.vue'
import PickerField from './PickerField.vue'
import { formatLongDate } from '../utils/date.js'
import { minBookableDate } from '../utils/bookingRules.js'

// modelValue is an ISO date ("YYYY-MM-DD") or an empty string.
defineProps({
  modelValue: { type: String, default: '' },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'toggle', 'close'])

function choose(isoDate) {
  emit('update:modelValue', isoDate)
  emit('close')
}
</script>

<template>
  <PickerField
    label="Date"
    :value="modelValue ? formatLongDate(modelValue) : ''"
    :open="open"
    panel-class="is-calendar"
    @toggle="emit('toggle')"
  >
    <BookingCalendar :min-date="minBookableDate()" :initial-date="modelValue" @select="choose" />
    <p class="picker-hint">Bookings must be made at least one day in advance.</p>
  </PickerField>
</template>
