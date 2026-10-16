import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { startCheckout } from '../services/payment.js'
import { useBookingsStore } from '../stores/bookings.js'
import { useVenuesStore } from '../stores/venues.js'
import { hasConflict, isBookableDate, takenHours } from '../utils/bookingRules.js'

export const TIME_UNAVAILABLE_MESSAGE = 'That time is unavailable.'

// State and rules for the booking form: facility, date (H-1 or later), whole-hour time range.
export function useBookingForm(initialDate = '') {
  const router = useRouter()
  const venuesStore = useVenuesStore()
  const bookingsStore = useBookingsStore()

  const facilityKey = ref('')
  const date = ref(isBookableDate(initialDate) ? initialDate : '')
  const startHour = ref(null)
  const endHour = ref(null)
  const timeNotice = ref('')
  const submitting = ref(false)

  const facility = computed(() => venuesStore.venues.find((venue) => venue.key === facilityKey.value) ?? null)

  const facilityOptions = computed(() =>
    venuesStore.venues.map((venue) => ({ ...venue, bookable: venuesStore.isBookable(venue.key) })),
  )

  const isFacilityBookable = computed(() => Boolean(facility.value) && venuesStore.isBookable(facility.value.key))

  // Hours already booked by other clients for the chosen facility and date.
  const taken = computed(() =>
    facility.value && date.value ? takenHours(bookingsStore.bookings, facility.value.label, date.value) : new Set(),
  )

  const hasTime = computed(() => startHour.value !== null && endHour.value !== null)
  const hours = computed(() => (hasTime.value ? endHour.value - startHour.value : 0))
  const hourlyRate = computed(() => (facility.value ? venuesStore.hourlyRate(facility.value.key) : 0))
  const total = computed(() => hourlyRate.value * hours.value)

  const canConfirm = computed(
    () =>
      isFacilityBookable.value &&
      Boolean(date.value) &&
      hasTime.value &&
      !hasConflict(taken.value, startHour.value, endHour.value),
  )

  // A previously chosen time that became taken (different facility/date, or a new booking) must be re-entered.
  watch(taken, (current) => {
    if (hasTime.value && hasConflict(current, startHour.value, endHour.value)) {
      startHour.value = null
      endHour.value = null
      timeNotice.value = `${TIME_UNAVAILABLE_MESSAGE} Please pick a new time.`
    }
  })

  function selectFacility(key) {
    facilityKey.value = key
  }

  function selectDate(isoDate) {
    if (isBookableDate(isoDate)) date.value = isoDate
  }

  // Returns false (and sets a notice) when the range overlaps a booking from another client.
  function selectTime(start, end) {
    if (hasConflict(taken.value, start, end)) {
      timeNotice.value = TIME_UNAVAILABLE_MESSAGE
      return false
    }
    startHour.value = start
    endHour.value = end
    timeNotice.value = ''
    return true
  }

  async function confirm() {
    if (!canConfirm.value || submitting.value) return
    submitting.value = true
    try {
      const { redirect } = await startCheckout({
        facilityKey: facility.value.key,
        facility: facility.value.label,
        date: date.value,
        startHour: startHour.value,
        endHour: endHour.value,
        hours: hours.value,
        hourlyRate: hourlyRate.value,
        total: total.value,
      })
      await router.push(redirect)
    } finally {
      submitting.value = false
    }
  }

  return {
    facilityKey,
    facility,
    facilityOptions,
    isFacilityBookable,
    date,
    startHour,
    endHour,
    taken,
    hasTime,
    hours,
    hourlyRate,
    total,
    timeNotice,
    canConfirm,
    submitting,
    selectFacility,
    selectDate,
    selectTime,
    confirm,
  }
}
