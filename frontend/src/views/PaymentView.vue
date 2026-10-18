<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useCheckoutStore } from '../stores/checkout.js'
import { errorDetail, fetchBooking, fetchClientConfig } from '../services/api.js'
import { formatHour, formatLongDate } from '../utils/date.js'

const POLL_MS = 5000

const router = useRouter()
const checkout = useCheckoutStore()
const order = computed(() => checkout.pendingOrder)
const gateway = computed(() => checkout.gateway)

const booking = ref(null)
const clientConfig = ref(null)
const secondsLeft = ref(null)
const lookUpError = ref('')
let pollTimer = null
let tickTimer = null

const settled = computed(() => {
  const status = booking.value?.status
  return status === 'confirmed' || status === 'cancelled'
})

const statusLine = computed(() => {
  if (!booking.value) return ''
  const status = booking.value.status
  const payment = booking.value.payment_status
  if (payment === 'paid') return 'Paid. The booking is confirmed, see you there.'
  if (payment === 'failed') {
    return 'The payment did not go through. The venue still has your hours: it can confirm the visit or release them.'
  }
  if (payment === 'refunded') return 'The money for this visit was sent back.'
  if (status === 'confirmed') return 'Confirmed by the venue. The payment is handled offline.'
  if (status === 'cancelled') return 'This booking was cancelled and the hours are free again.'
  return ''
})

const countdown = computed(() => {
  if (secondsLeft.value === null) return ''
  const total = Math.max(secondsLeft.value, 0)
  const minutes = Math.floor(total / 60)
  const seconds = String(total % 60).padStart(2, '0')
  return `Held for ${minutes}:${seconds} more`
})

const notice = computed(() => {
  if (!order.value || settled.value) return ''
  switch (gateway.value?.status) {
    case 'ready':
      return 'Your booking is held. Finish the payment to confirm it.'
    case 'unconfigured':
      return 'This server has no payment keys set yet, so no invoice could be opened. Your booking stays pending until the manager confirms it.'
    case 'failed':
      return 'The payment session could not be opened. Your booking stays pending until the manager confirms it.'
    default:
      return ''
  }
})

function openCheckout() {
  if (gateway.value?.checkout_url) window.open(gateway.value.checkout_url, '_blank', 'noopener')
}

async function refresh() {
  const bookingId = order.value?.bookingId
  if (!bookingId) return
  try {
    booking.value = await fetchBooking(bookingId)
    secondsLeft.value = booking.value.expires_in_seconds
    // Stop polling once the booking can no longer change on its own.
    if (settled.value) stopPolling()
  } catch (err) {
    lookUpError.value = errorDetail(err, 'Could not read the booking status.')
    stopPolling()
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function tick() {
  if (secondsLeft.value === null) return
  secondsLeft.value = Math.max(secondsLeft.value - 1, 0)
}

function startWatching(bookingId) {
  if (!bookingId || pollTimer) return
  pollTimer = setInterval(refresh, POLL_MS)
  tickTimer = setInterval(tick, 1000)
}

onMounted(async () => {
  try {
    clientConfig.value = await fetchClientConfig()
  } catch {
    clientConfig.value = null
  }
  await refresh()
  startWatching(order.value?.bookingId)
})

// The order can arrive after the page did (the booking redirect lands here), so
// the status watch starts whenever a booking id shows up, not only on mount.
watch(
  () => order.value?.bookingId,
  async (bookingId) => {
    if (!bookingId) return
    await refresh()
    startWatching(bookingId)
  }
)

onBeforeUnmount(() => {
  stopPolling()
  if (tickTimer) clearInterval(tickTimer)
})
</script>

<template>
  <section class="mx-auto max-w-md space-y-4 text-center">
    <h1 class="text-3xl font-bold tracking-tight text-gray-900">Payment</h1>

    <div v-if="order" class="space-y-1 rounded-2xl border border-gray-300 bg-white p-5 text-left">
      <p class="font-semibold">{{ order.facility }}</p>
      <p class="text-sm text-gray-600">{{ formatLongDate(order.date) }}</p>
      <p class="text-sm text-gray-600">{{ formatHour(order.startHour) }} - {{ formatHour(order.endHour) }}</p>
      <p class="pt-2 text-sm text-gray-600">{{ order.hourlyRate }} /hour x {{ order.hours }}</p>
      <p class="font-bold">Total: {{ order.total }}</p>
      <p v-if="gateway?.invoice_number" class="text-xs text-gray-500">
        Invoice {{ gateway.invoice_number }}
      </p>
      <p v-if="order.bookingId" class="text-xs text-gray-500">Booking {{ order.bookingId }}</p>
    </div>
    <p v-else class="text-gray-600">There is nothing to pay for yet.</p>

    <div v-if="statusLine" class="rounded-2xl border border-gray-300 bg-white p-4 text-left">
      <p class="text-sm font-semibold text-gray-900">
        {{ booking.payment_status === 'paid' ? 'Paid' : booking.status === 'confirmed' ? 'Confirmed' : 'Cancelled' }}
      </p>
      <p class="text-sm text-gray-600">{{ statusLine }}</p>
      <p v-if="booking.payment_invoice_number" class="text-xs text-gray-500">
        Invoice {{ booking.payment_invoice_number }}
      </p>
    </div>

    <p v-if="!settled && countdown" class="text-sm font-semibold text-gray-700">{{ countdown }}</p>
    <p v-if="!settled" class="text-xs text-gray-500">
      This page checks the status by itself every {{ POLL_MS / 1000 }} seconds.
    </p>
    <p v-if="lookUpError" class="text-sm text-red-600" role="alert">{{ lookUpError }}</p>

    <p v-if="notice" class="text-sm text-gray-600">{{ notice }}</p>
    <p v-if="clientConfig && !clientConfig.payment_configured" class="text-xs text-gray-500">
      Online payment is switched off on this server.
    </p>

    <button
      v-if="gateway?.status === 'ready' && !settled"
      type="button"
      class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold"
      @click="openCheckout"
    >
      Open the payment page
    </button>

    <button
      type="button"
      class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold"
      @click="router.push({ name: 'my-bookings' })"
    >
      My bookings
    </button>

    <button
      type="button"
      class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold"
      @click="router.push({ name: 'booking' })"
    >
      Back to booking
    </button>
  </section>
</template>
