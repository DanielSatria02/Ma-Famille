<script setup>
import { computed, ref } from 'vue'
import { parseIsoDate, toIsoDate } from '../utils/date.js'
import '../styles/calendar.css'

const props = defineProps({
  allowPastMonths: { type: Boolean, default: false },
  // ISO dates ("YYYY-MM-DD") that have at least one booking.
  bookedDates: { type: Array, default: () => [] },
  // When true, shows a "Book now?" button and lets a double-click on a date open booking.
  bookable: { type: Boolean, default: false },
  // ISO date; dates before it cannot be selected.
  minDate: { type: String, default: '' },
  // ISO date to start on. Omit for today; pass an empty string for no selection.
  initialDate: { type: String, default: undefined },
})

const emit = defineEmits(['book', 'select'])

const bookedDateSet = computed(() => new Set(props.bookedDates))

const today = new Date()
const startDate = props.initialDate ? parseIsoDate(props.initialDate) : null
const selectedDate = ref(props.initialDate === undefined ? createDate(today) : startDate)
const displayedMonth = ref(new Date((startDate ?? today).getFullYear(), (startDate ?? today).getMonth(), 1))
const currentMonth = new Date(today.getFullYear(), today.getMonth(), 1)

const isPreviousMonthDisabled = computed(
  () => !props.allowPastMonths && displayedMonth.value <= currentMonth,
)

const monthLabel = computed(() => displayedMonth.value.toLocaleDateString('en-US', {
  month: 'long',
  year: 'numeric',
}))

const calendarDays = computed(() => {
  const year = displayedMonth.value.getFullYear()
  const month = displayedMonth.value.getMonth()
  const firstDayIndex = (new Date(year, month, 1).getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  return Array.from({ length: 42 }, (_, index) => {
    const dayNumber = index - firstDayIndex + 1
    if (dayNumber < 1 || dayNumber > daysInMonth) return null

    const date = new Date(year, month, dayNumber)
    return {
      date,
      dayNumber,
      isToday: isSameDate(date, today),
      isSelected: selectedDate.value !== null && isSameDate(date, selectedDate.value),
      isBooked: bookedDateSet.value.has(toIsoDate(date)),
      isDisabled: Boolean(props.minDate) && toIsoDate(date) < props.minDate,
    }
  })
})

function createDate(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function isSameDate(firstDate, secondDate) {
  return firstDate.toDateString() === secondDate.toDateString()
}

function changeMonth(monthOffset) {
  if (monthOffset < 0 && isPreviousMonthDisabled.value) return

  displayedMonth.value = new Date(
    displayedMonth.value.getFullYear(),
    displayedMonth.value.getMonth() + monthOffset,
    1,
  )
}

function selectDate(day) {
  if (!day || day.isDisabled) return
  selectedDate.value = day.date
  emit('select', toIsoDate(day.date))
}

function bookDate(day) {
  if (!props.bookable || !day || day.isDisabled) return
  selectedDate.value = day.date
  emit('book', toIsoDate(day.date))
}
</script>

<template>
  <section class="calendar" aria-labelledby="calendar-title">
    <div class="calendar-header">
      <div>
        <p class="calendar-eyebrow">Availability</p>
        <h2 id="calendar-title" class="calendar-title">Choose a date</h2>
      </div>
      <div class="calendar-navigation">
        <button
          type="button"
          class="calendar-nav-button"
          :aria-label="isPreviousMonthDisabled ? 'Previous month unavailable' : 'Previous month'"
          :disabled="isPreviousMonthDisabled"
          @click="changeMonth(-1)"
        >
          <span aria-hidden="true">&#8249;</span>
        </button>
        <p class="calendar-month" aria-live="polite">{{ monthLabel }}</p>
        <button type="button" class="calendar-nav-button" aria-label="Next month" @click="changeMonth(1)">
          <span aria-hidden="true">&#8250;</span>
        </button>
      </div>
    </div>

    <div class="calendar-weekdays" aria-hidden="true">
      <span v-for="weekday in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']" :key="weekday">
        {{ weekday }}
      </span>
    </div>

    <div class="calendar-grid" role="grid" aria-label="Calendar dates">
      <button
        v-for="(day, index) in calendarDays"
        :key="day ? day.date.toISOString() : `empty-${index}`"
        type="button"
        class="calendar-day"
        :class="{
          'is-today': day?.isToday,
          'is-selected': day?.isSelected,
          'is-booked': day?.isBooked,
          'is-disabled': day?.isDisabled,
        }"
        :disabled="!day || day.isDisabled"
        :aria-label="day ? `${day.date.toLocaleDateString('en-US', { dateStyle: 'full' })}${day.isBooked ? ', has bookings' : ''}` : undefined"
        :aria-pressed="day?.isSelected"
        @click="selectDate(day)"
        @dblclick="bookDate(day)"
      >
        <span class="calendar-day-number">{{ day?.dayNumber }}</span>
      </button>
    </div>

    <p v-if="selectedDate" class="calendar-selection" aria-live="polite">
      Selected: {{ selectedDate.toLocaleDateString('en-US', { dateStyle: 'long' }) }}
    </p>

    <div v-if="bookable && selectedDate" class="calendar-actions">
      <button type="button" class="calendar-book-button" @click="emit('book', toIsoDate(selectedDate))">
        Book now?
      </button>
    </div>
  </section>
</template>