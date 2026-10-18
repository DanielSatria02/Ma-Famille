import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import {
  checkPromotion,
  createRangeBooking,
  errorDetail,
  errorStatus,
  fetchDayAvailability,
  fetchQuote,
} from '../services/api.js'
import { startCheckout } from '../services/payment.js'
import { setCustomerContact } from '../services/session.js'
import { useVenuesStore } from '../stores/venues.js'
import { hasConflict, isBookableDate } from '../utils/bookingRules.js'
import { formatLongDate } from '../utils/date.js'

export const TIME_UNAVAILABLE_MESSAGE = 'That time is unavailable.'

const pad = (hour) => String(hour).padStart(2, '0')

// State and rules for the booking form: facility, date (H-1 or later), whole-hour
// range. Availability, the price and the booking itself all come from the API;
// the checks here only keep the UI from offering something the server rejects.
export function useBookingForm(initialDate = '', initialFacilityKey = '') {
  const router = useRouter()
  const venuesStore = useVenuesStore()

  const facilityKey = ref('')
  const date = ref(isBookableDate(initialDate) ? initialDate : '')
  // A link can carry a date that has since become unbookable — yesterday's
  // "book soonest free day" link, or a shared URL opened after midnight. Saying
  // so beats an empty date field that looks like the page forgot the choice.
  const droppedDate = ref(
    initialDate && !isBookableDate(initialDate) ? formatLongDate(initialDate) : '',
  )
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

  // Promo code as typed, plus the server's dry-run verdict on it. The check is
  // advisory — the booking re-verifies the code — but it is what draws the
  // discount line and what tells the customer why a code will not work.
  const promoCode = ref('')
  const promoResult = ref(null)
  const promoChecking = ref(false)
  const promoError = ref('')

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

  // Hours the client cannot start a booking in. The API only lists the hours
  // inside the opening window and flags the taken ones, so everything else is
  // blocked too — a booking needs a free slot row on the hour it starts.
  const taken = computed(() => {
    const blocked = new Set()
    if (availabilityError.value) return blocked
    const free = new Set(
      dayHours.value.filter((entry) => entry.status === 'available').map((entry) => entry.hour),
    )
    for (let hour = 0; hour < 23; hour += 1) {
      if (!free.has(hour)) blocked.add(hour)
    }
    return blocked
  })

  const hasTime = computed(() => startHour.value !== null && endHour.value !== null)
  const hours = computed(() => (hasTime.value ? endHour.value - startHour.value : 0))
  // Opening window of the chosen day, shown as a hint next to the time picker.
  const openWindow = computed(() => {
    if (isClosed.value) return 'Closed on that date'
    const free = dayHours.value.filter((entry) => entry.status === 'available')
    if (!free.length) return 'No hours left on that date'
    const first = free[0].hour
    const last = free[free.length - 1].hour + 1
    return `Bookable ${pad(first)}:00 - ${pad(last)}:00`
  })
  const hourlyRate = computed(() =>
    facility.value ? venuesStore.hourlyRate(facility.value.key, date.value) : 0,
  )
  // The server quote wins: a weekend range can mix rates.
  const gross = computed(() => quote.value?.total ?? hourlyRate.value * hours.value)
  const promoAccepted = computed(() => promoResult.value?.ok === true)
  const promoRefused = computed(
    () => Boolean(promoCode.value) && promoResult.value?.ok === false,
  )
  // Send the code whenever the box has one and the server has not said no.
  // A failed check (server unreachable) must not silently drop the discount the
  // customer asked for — the booking re-verifies it and answers 422 if wrong.
  const promoToSend = computed(() =>
    Boolean(promoCode.value) && !promoRefused.value ? promoCode.value.trim() : null,
  )
  // The line the customer sees: what the code took off this range.
  const promoDiscount = computed(() =>
    promoAccepted.value ? promoResult.value.discount : 0,
  )
  const total = computed(() => Math.max(0, gross.value - promoDiscount.value))

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
      !promoRefused.value &&
      !promoChecking.value &&
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

  // Ask the server what the code does. Debounced so typing H-E-M-A-T does not
  // fire five requests, and dropped entirely when the box is empty.
  let promoTimer = null
  async function runPromoCheck() {
    const code = promoCode.value.trim()
    if (!code) {
      promoResult.value = null
      promoError.value = ''
      promoChecking.value = false
      return
    }
    // Without a range there is nothing to discount yet; the code alone can
    // still be checked so an unknown one is reported immediately.
    const hasRange = Boolean(facilityKey.value && date.value && hasTime.value)
    promoChecking.value = true
    promoError.value = ''
    try {
      promoResult.value = await checkPromotion({
        code,
        courtPublicId: hasRange ? facilityKey.value : undefined,
        startsAt: hasRange ? `${date.value}T${pad(startHour.value)}:00:00` : undefined,
        endsAt: hasRange ? `${date.value}T${pad(endHour.value)}:00:00` : undefined,
      })
    } catch (err) {
      // A failed check is not a verdict: leave the box usable and say why.
      promoResult.value = null
      promoError.value = errorDetail(err, 'Could not check that code.')
    } finally {
      promoChecking.value = false
    }
  }
  function schedulePromoCheck() {
    clearTimeout(promoTimer)
    promoTimer = setTimeout(runPromoCheck, 350)
  }
  watch(promoCode, schedulePromoCheck)
  // A new range changes what the code is worth, so re-run for the same code.
  watch([facilityKey, date, startHour, endHour], () => {
    if (promoCode.value.trim()) schedulePromoCheck()
  })
  onUnmounted(() => clearTimeout(promoTimer))

  // Deep link from the home page: preselect that facility once the list is in.
  watch(
    () => [venuesStore.facilities.length, initialFacilityKey],
    () => {
      if (!initialFacilityKey || facilityKey.value) return
      if (venuesStore.facilities.some((entry) => entry.public_id === initialFacilityKey)) {
        facilityKey.value = initialFacilityKey
      }
    },
    { immediate: true },
  )

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
    if (isBookableDate(isoDate)) {
      date.value = isoDate
      // The visitor has picked something valid, so the stale link is no longer
      // worth mentioning.
      droppedDate.value = ''
    }
  }

  // Returns false (and sets a notice) when the range overlaps a taken hour.
  function selectTime(start, end) {
    // Normalise at the door: the picker hands over whatever the <select> gave
    // it, and a non-numeric value would otherwise travel all the way into the
    // quote URL (`Tundefined:00:00`) and render as "NaN hours" in the summary.
    const startHourNum = Number(start)
    const endHourNum = Number(end)
    if (!Number.isInteger(startHourNum) || !Number.isInteger(endHourNum) || endHourNum <= startHourNum) {
      timeNotice.value = `${TIME_UNAVAILABLE_MESSAGE} Please pick a new time.`
      return false
    }
    if (hasConflict(taken.value, startHourNum, endHourNum)) {
      timeNotice.value = TIME_UNAVAILABLE_MESSAGE
      return false
    }
    startHour.value = startHourNum
    endHour.value = endHourNum
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
        // A refused code is blocked by `canConfirm`; anything else goes through
        // and the server re-verifies it, so a failed check cannot silently
        // charge full price for a booking that asked for a discount.
        ...(promoToSend.value ? { promo_code: promoToSend.value } : {}),
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
        // `created.total` is already net of the discount.
        total: created.total,
        ...(created.bookings[0].discount
          ? { discount: created.bookings[0].discount, promoCode: created.bookings[0].promo_code }
          : {}),
      }
      // The hours just booked are no longer free.
      await loadDay()
      // Remember the contact: it is what lets the client find and cancel this visit.
      setCustomerContact(customerContact.value.trim())
      startHour.value = null
      endHour.value = null
      // The code was redeemed with that booking; do not carry it to the next one.
      promoCode.value = ''
      promoResult.value = null
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
    openWindow,
    hourlyRate,
    total,
    gross,
    quote,
    promoCode,
    promoResult,
    promoChecking,
    promoError,
    promoAccepted,
    promoRefused,
    promoToSend,
    promoDiscount,
    isClosed,
    timeNotice,
    droppedDate,
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
