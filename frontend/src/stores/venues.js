import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

// Single source of truth for venue status and hourly prices, shared by the manager and booking pages.
// To be loaded from and saved to the API later.
export const useVenuesStore = defineStore('venues', () => {
  // null price means no price set: unavailable for booking (not free). Venues without a key here have no rate.
  const prices = ref({ arena: 100000, office: 100000 })

  const venues = ref([
    { key: 'cafe', label: 'Cafe', available: true },
    { key: 'office', label: 'Office', available: true },
    { key: 'arena', label: 'Padel Arena', available: true },
  ])

  const hasPrice = (key) => key in prices.value

  function isBookable(key) {
    const venue = venues.value.find((entry) => entry.key === key)
    if (!venue?.available) return false
    return !hasPrice(key) || prices.value[key] !== null
  }

  function hourlyRate(key) {
    return hasPrice(key) ? prices.value[key] : 0
  }

  // An unavailable venue shows no price in the manager's pricing panel.
  const pricing = computed(() =>
    [
      { key: 'arena', label: 'Arena' },
      { key: 'office', label: 'Office' },
    ].map((item) => ({ ...item, price: isBookable(item.key) ? prices.value[item.key] : null })),
  )

  const venueStatusItems = computed(() =>
    venues.value.map((venue) => ({
      ...venue,
      locked: hasPrice(venue.key) && prices.value[venue.key] === null,
    })),
  )

  function updatePricing({ key, price }) {
    const venue = venues.value.find((entry) => entry.key === key)
    if (!venue) return
    if (price === null) {
      prices.value[key] = null
      venue.available = false
      return
    }
    // Setting a price after a reset brings the venue back.
    if (prices.value[key] === null) venue.available = true
    prices.value[key] = price
  }

  function toggleVenue({ key, available }) {
    const venue = venues.value.find((entry) => entry.key === key)
    if (venue) venue.available = available
  }

  return { prices, venues, pricing, venueStatusItems, isBookable, hourlyRate, updatePricing, toggleVenue }
})
