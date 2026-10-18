import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { errorDetail, fetchFacilities, fetchManagerFacilities, updateCourt } from '../services/api.js'

// Facilities are the backend's `courts` rows: the single source of truth for
// what a client can book (availability + rate) and for the manager panels.
// `public_id` is the key every view uses.
export const useVenuesStore = defineStore('venues', () => {
  const facilities = ref([])
  const loading = ref(false)
  const error = ref('')

  const venues = computed(() =>
    facilities.value.map((facility) => ({
      key: facility.public_id,
      label: facility.name,
      available: facility.is_bookable,
    })),
  )

  const activeVenue = computed(() => facilities.value[0] ?? null)

  function byKey(key) {
    return facilities.value.find((facility) => facility.public_id === key) ?? null
  }

  function isBookable(key) {
    return Boolean(byKey(key)?.is_bookable)
  }

  // Why a facility cannot be booked, in the client's words.
  function unavailableNote(key) {
    const facility = byKey(key)
    if (!facility) return ''
    if (!facility.is_active || facility.unavailable_reason === 'inactive') return 'Closed'
    if (!facility.is_price_set || facility.unavailable_reason === 'no_rate') return 'No price set'
    return ''
  }

  // Weekend rates apply on Saturday and Sunday, like the backend.
  function isWeekend(isoDate) {
    const [year, month, day] = isoDate.split('-').map(Number)
    return new Date(Date.UTC(year, month - 1, day)).getUTCDay() >= 5
  }

  function hourlyRate(key, isoDate = '') {
    const facility = byKey(key)
    if (!facility || !facility.is_price_set) return 0
    const weekend = isoDate ? isWeekend(isoDate) : false
    const rate = weekend ? facility.price_weekend : facility.price_weekday
    return rate ?? facility.price_weekday ?? facility.price_weekend ?? 0
  }

  // Manager pricing panel: facilities that sell hours (the cafe is not bookable time).
  const pricing = computed(() =>
    facilities.value
      .filter((facility) => facility.kind !== 'cafe')
      .map((facility) => ({
        key: facility.public_id,
        label: facility.name,
        price: facility.is_price_set ? facility.price_weekday ?? facility.price_weekend : null,
      })),
  )

  // Manager venue-status panel: `locked` = cannot be switched on until priced.
  const venueStatusItems = computed(() =>
    facilities.value.map((facility) => ({
      key: facility.public_id,
      label: facility.name,
      available: facility.is_active,
      locked: facility.locked ?? !facility.is_price_set,
    })),
  )

  // A court row comes back without the facility roll-ups, so recompute them.
  function applyCourt(entry, court) {
    const merged = { ...entry, ...court }
    merged.is_bookable = Boolean(merged.is_active && merged.is_price_set)
    merged.locked = !merged.is_price_set
    if (merged.is_price_set) merged.unavailable_reason = null
    else merged.unavailable_reason = 'no_rate'
    return merged
  }

  async function load(params = {}) {
    loading.value = true
    error.value = ''
    try {
      facilities.value = await fetchFacilities(params)
    } catch (err) {
      error.value = errorDetail(err, 'Could not load the facilities.')
      facilities.value = []
    } finally {
      loading.value = false
    }
  }

  // Same listing plus `locked`, so the manager sees what is missing a rate.
  async function loadForManager(params = {}) {
    loading.value = true
    error.value = ''
    try {
      facilities.value = await fetchManagerFacilities(params)
    } catch (err) {
      error.value = errorDetail(err, 'Could not load the facilities.')
      facilities.value = []
    } finally {
      loading.value = false
    }
  }

  async function updatePricing({ key, price }) {
    const facility = byKey(key)
    if (!facility) return
    error.value = ''
    try {
      const patch =
        price === null
          ? { price_weekday: null, price_weekend: null }
          : {
              price_weekday: price,
              price_weekend: price,
              // Setting a rate after a reset brings the facility back.
              ...(facility.is_price_set ? {} : { is_active: true }),
            }
      const updated = await updateCourt(key, patch)
      facilities.value = facilities.value.map((entry) => (entry.public_id === key ? applyCourt(entry, updated) : entry))
    } catch (err) {
      error.value = errorDetail(err, 'Could not save the price.')
    }
  }

  async function toggleVenue({ key, available }) {
    error.value = ''
    try {
      const updated = await updateCourt(key, { is_active: available })
      facilities.value = facilities.value.map((entry) => (entry.public_id === key ? applyCourt(entry, updated) : entry))
    } catch (err) {
      error.value = errorDetail(err, 'Could not update the facility.')
    }
  }

  return {
    facilities,
    loading,
    error,
    venues,
    activeVenue,
    pricing,
    venueStatusItems,
    byKey,
    isBookable,
    unavailableNote,
    hourlyRate,
    load,
    loadForManager,
    updatePricing,
    toggleVenue,
  }
})
