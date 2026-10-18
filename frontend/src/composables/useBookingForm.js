import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import {
  createRangeBooking,
  errorDetail,
  errorStatus,
  fetchDayAvailability,
  fetchQuote,
} from '../services/api.js'
import { startCheckout } from '../services/payment.js'
import { useVenuesStore } from '../stores/venues.js'
import { hasConflict, isBookableDate } from '../utils/bookingRules.js'

export const TIME_UNAVAILABLE_MESSAGE = 'That time is unavailable.'

const pad = (hour) => String(hour).padStart(2, '0')

// State and rules for the booking form: facility, date (H-1 or later), whole-hour
// range. Availability, the price and the booking itself all come from the API;
// the checks here only keep the UI from offering something the server rejects.
export function useBookingForm(initialDate = '') {
  const router = useRouter()
  const venuesStore = useVenuesStore()

  const facilityKey = ref('')
  const date = ref(isBookableDate(initialDate) ? initialDate : '')
  const startHour = ref(null)
  const endHour = ref(null)
  const customerName = ref('')
  const customerContact = ref('')
  const timeNotice = ref('')
  const availabilityError = ref('')
  const submitError = ref('')
  const submitting = ref(false)
  const dayHours = ref([])
  const isClosed = ref(false)
  const quote = ref(null)

  const facility = computed(
    () => venuesStore.venues.find((venue) => venue.key === facilityKey.value) ?? null,
  )

  const facilityOptions = computed(() =>
    venuesStore.venues.map((venue) => ({
      ...venue,
      bookable: venuesStore.isBookable(venue.key),
      note: venuesStore.unavailableNote(venue.key),
    })),
  )

  const isFacilityBookable = computed(
    () => Boolean(facility.value) && venuesStore.isBookable(facility.value.key),
  )

  // Hours the client cannot start a booking in: booked, held, blocked, or no
  // slot generated for that hour yet.
  const taken = computed(
    () => new Set(dayHours.value.filter((entry) => entry.status !== 'available').map((entry) => entry.hour)),
  )

  const hasTime = computed(() => startHour.value !== null && endHour.value !== null)
  const hours = computed(() => (hasTime.value ? endHour.value - startHour.value : 0))
  const hourlyRate = computed(() =>
    facility.value ? venuesStore.hourlyRate(facility.value.key, date.value) : 0,
  )
  // The server quote wins: a weekend range can mix rates.
  const total = computed(() => quote.value?.total ?? hourlyRate.value * hours.value)

  const hasCustomer = computed(
    () => customerName.value.trim().length > 0 && customerContact.value.trim().length >= 3,
  )

  const canConfirm = computed(
    () =>
      isFacilityBookable.value &&
      Boolean(date.value) &&
      hasTime.value &&
      !isClosed.value &&
      hasCustomer.value &&
      !hasConflict(taken.value, startHour.value, endHour.value),
  )

  async function loadDay() {
    if (!facilityKey.value || !date.value) {
      dayHours.value = []
      return
    }
    try {
      const data = await fetchDayAvailability(facilityKey.value, date.value)
      dayHours.value = data.hours
      isClosed.value = data.is_closed
      availabilityError.value = ''
    } catch (err) {
      dayHours.value = []
      availabilityError.value = errorDetail(err, 'Could not load availability.')
    }
  }

  async function loadQuote() {
    if (!facilityKey.value || !date.value || !hasTime.value) {
      quote.value = null
      return
    }
    try {
      quote.value = await fetchQuote(
        facilityKey.value,
        `${date.value}T${pad(startHour.value)}:00:00`,
        `${date.value}T${pad(endHour.value)}:00:00`,
      )
    } catch {
      // Keep the local estimate when the quote is refused (e.g. half-hour range).
      quote.value = null
    }
  }

  watch([facilityKey, date], loadDay, { immediate: true })
  watch([facilityKey, date, startHour, endHour], loadQuote)

  // A previously chosen time that became taken (different facility/date, or a new
  // booking) must be re-entered.
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

  // Returns false (and sets a notice) when the range overlaps a taken hour.
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
    submitError.value = ''
    try {
      const created = await createRangeBooking({
        court_public_id: facility.value.key,
        starts_at: `${date.value}T${pad(startHour.value)}:00:00`,
        ends_at: `${date.value}T${pad(endHour.value)}:00:00`,
        customer_name: customerName.value.trim(),
        customer_contact: customerContact.value.trim(),
      })
      const order = {
        bookingId: created.bookings[0].public_id,
        groupId: created.group_public_id,
        facilityKey: facility.value.key,
        facility: facility.value.label,
        date: date.value,
        startHour: startHour.value,
        endHour: endHour.value,
        hours: created.hours,
        hourlyRate: quote.value?.hourly_rate ?? hourlyRate.value,
        total: created.total,
      }
      // The hours just booked are no longer free.
      await loadDay()
      startHour.value = null
      endHour.value = null
      const { redirect } = await startCheckout(order)
      await router.push(redirect)
    } catch (err) {
      if (errorStatus(err) === 409) {
        submitError.value = `${errorDetail(err, TIME_UNAVAILABLE_MESSAGE)} Please pick a new time.`
        startHour.value = null
        endHour.value = null
        await loadDay()
      } else {
        submitError.value = errorDetail(err, 'The booking could not be created.')
      }
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
    customerName,
    customerContact,
    taken,
    hasTime,
    hours,
    hourlyRate,
    total,
    quote,
    isClosed,
    timeNotice,
    availabilityError,
    submitError,
    canConfirm,
    submitting,
    selectFacility,
    selectDate,
    selectTime,
    confirm,
  }
}
