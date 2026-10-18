<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useCheckoutStore } from '../stores/checkout.js'
import { errorDetail, fetchBooking, fetchClientConfig } from '../services/api.js'
import { watchBooking } from '../services/live.js'
import { formatHour, formatLongDate } from '../utils/date.js'
import '../styles/payment.css'

// The hold countdown is the one timer left in the app, and it is not polling:
// it counts down a number the server already gave us, between two pushed
// updates. The status itself arrives over a socket.
const COUNTDOWN_MS = 1000

const router = useRouter()
const checkout = useCheckoutStore()
const order = computed(() => checkout.pendingOrder)
const gateway = computed(() => checkout.gateway)

const booking = ref(null)
const clientConfig = ref(null)
const secondsLeft = ref(null)
const lookUpError = ref('')
// 'connecting' | 'live' | 'offline' — shown so a stale screen is never
// mistaken for an unchanged booking.
const connection = ref('connecting')
let stopWatching = null
let tickTimer = null

const settled = computed(() => {
  const status = booking.value?.status
  return status === 'confirmed' || status === 'cancelled'
})

// One card, one state. The three buttons this page used to have were styled
// identically — "open the payment page" next to "back to booking", a tap apart,
// both plain outlined rectangles. On the one screen where someone's money is
// about to move, the way out and the way on have to look different.
const state = computed(() => {
  const payment = booking.value?.payment_status
  const status = booking.value?.status
  if (payment === 'paid') {
    return { tone: 'paid', title: 'Paid', text: 'The booking is confirmed. See you there.' }
  }
  if (payment === 'failed') {
    return {
      tone: 'failed',
      title: 'Payment failed',
      text: 'No money moved. The venue still has your hours and can confirm the visit or release them — try again from My bookings.',
    }
  }
  if (payment === 'refunded') {
    return { tone: 'neutral', title: 'Refunded', text: 'The money for this visit was sent back.' }
  }
  if (status === 'confirmed') {
    return {
      tone: 'neutral',
      title: 'Confirmed',
      text: 'The venue confirmed this visit. The payment is handled offline.',
    }
  }
  if (status === 'cancelled') {
    return {
      tone: 'failed',
      title: 'Cancelled',
      text: 'This booking was cancelled and the hours are free again.',
    }
  }
  if (booking.value) {
    // statusLine has nothing to say here: every branch above is a settled
    // state, so this is the one case it would return an empty string for and
    // leave the card reading as a heading with nothing under it.
    return {
      tone: 'pending',
      title: 'Waiting for payment',
      text: 'The hours are held for you until the timer runs out. Nothing is charged until you pay.',
    }
  }
  return null
})

const countdown = computed(() => {
  if (secondsLeft.value === null) return ''
  const total = Math.max(secondsLeft.value, 0)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
})

// Shown when this server cannot take a payment. The reason on the server
// ("payment_problem") names the setting that is wrong, which is for whoever is
// deploying, not for a visitor who only needs to know their booking is safe and
// someone will confirm it.
const paymentOff = computed(() => {
  if (!clientConfig.value || clientConfig.value.payment_configured) return ''
  return 'Online payment is not available on this server right now. Your booking is held and the venue will confirm it.'
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

function applySnapshot(payload) {
  booking.value = payload
  secondsLeft.value = payload.expires_in_seconds
  // Nothing left to wait for once the booking can no longer change on its
  // own, so the socket has done its job.
  stopWatchingIfSettled()
}

// The first read is over HTTP: it renders immediately, before a socket has
// finished opening, and it is the one call that can fail loudly.
async function refresh() {
  const bookingId = order.value?.bookingId
  if (!bookingId) return
  try {
    booking.value = await fetchBooking(bookingId)
    secondsLeft.value = booking.value.expires_in_seconds
    stopWatchingIfSettled()
  } catch (err) {
    lookUpError.value = errorDetail(err, 'Could not read the booking status.')
  }
}

function tick() {
  if (secondsLeft.value === null) return
  secondsLeft.value = Math.max(secondsLeft.value - 1, 0)
}

function startWatching(bookingId) {
  if (!bookingId || stopWatching) return
  stopWatching = watchBooking(bookingId, {
    onUpdate: applySnapshot,
    onStatus: (state) => {
      connection.value = state
    },
  })
  if (!tickTimer) tickTimer = setInterval(tick, COUNTDOWN_MS)
}

function closeWatch() {
  if (stopWatching) {
    stopWatching()
    stopWatching = null
  }
}

// The socket stops itself once the booking settles, and the page stops it on
// the way out — both routes named apart from the connection handle so neither
// shadows the other.
function stopWatchingIfSettled() {
  if (settled.value) closeWatch()
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
// the watch starts whenever a booking id shows up, not only on mount.
watch(
  () => order.value?.bookingId,
  async (bookingId) => {
    if (!bookingId) return
    await refresh()
    startWatching(bookingId)
  }
)

onBeforeUnmount(() => {
  closeWatch()
  if (tickTimer) clearInterval(tickTimer)
})
</script>

<template>
  <section class="payment">
    <h1 class="payment-title">Payment</h1>

    <div v-if="order" class="payment-card">
      <span class="payment-card-name">{{ order.facility }}</span>
      <span class="payment-card-line">{{ formatLongDate(order.date) }}</span>
      <span class="payment-card-line"
        >{{ formatHour(order.startHour) }} - {{ formatHour(order.endHour) }}</span
      >
      <span class="payment-card-line">{{ order.hourlyRate }} /hour x {{ order.hours }}</span>
      <span class="payment-card-total">Total: {{ order.total }}</span>
      <span v-if="gateway?.invoice_number" class="payment-card-ref">
        Invoice {{ gateway.invoice_number }}
      </span>
      <span v-if="order.bookingId" class="payment-card-ref">
        Booking {{ order.bookingId }}
      </span>
    </div>
    <p v-else class="payment-empty">There is nothing to pay for yet.</p>

    <!--
      Paid, failed, cancelled, still waiting: one card, one colour. Someone
      checking whether the money went through should not have to read the
      sentence to know, and should not have to notice the difference between two
      grey boxes.
    -->
    <div v-if="state" class="payment-state" :class="`is-${state.tone}`" role="status">
      <svg
        v-if="state.tone === 'paid'"
        class="payment-state-icon"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.86-9.36a.75.75 0 10-1.06-1.06L9.75 11.44 7.22 8.9a.75.75 0 00-1.06 1.06l3 3a.75.75 0 001.06 0l3.64-3.64z"
          clip-rule="evenodd"
        />
      </svg>
      <svg
        v-else-if="state.tone === 'failed'"
        class="payment-state-icon"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.94 6.94a.75.75 0 00-1.06 1.06L10.94 10l-3.06 3.06a.75.75 0 101.06 1.06L12 11.06l3.06 3.06a.75.75 0 001.06-1.06L13.06 10l3.06-3.06a.75.75 0 00-1.06-1.06L12 8.94 8.94 6.94z"
          clip-rule="evenodd"
        />
      </svg>
      <svg
        v-else
        class="payment-state-icon"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v3.5a1 1 0 002 0V7zm-1 7a1 1 0 100-2 1 1 0 000 2z"
          clip-rule="evenodd"
        />
      </svg>
      <div class="payment-state-body">
        <span class="payment-state-title">{{ state.title }}</span>
        <span v-if="state.text" class="payment-state-text">{{ state.text }}</span>
        <span v-if="booking?.payment_invoice_number" class="payment-card-ref">
          Invoice {{ booking.payment_invoice_number }}
        </span>
      </div>
    </div>

    <!-- The hold, on its own row with the number in a fixed width so it does
         not shuffle sideways once a second. -->
    <p v-if="!settled && countdown" class="payment-hold">
      <span>Held for</span>
      <span class="payment-hold-time">{{ countdown }}</span>
    </p>

    <!--
      Only while the status can still change. A settled booking has nothing
      left to hear about, so saying "live" there would be a claim, not a fact.
    -->
    <p v-if="!settled && order?.bookingId" class="payment-connection" role="status">
      <span class="payment-connection-dot" :class="`is-${connection}`" />
      <span v-if="connection === 'live'">Updating live</span>
      <span v-else-if="connection === 'connecting'">Connecting...</span>
      <span v-else>Reconnecting...</span>
    </p>

    <p v-if="lookUpError" class="payment-note" role="alert">{{ lookUpError }}</p>
    <p v-if="notice" class="payment-note">{{ notice }}</p>
    <p v-if="paymentOff" class="payment-off" role="status">
      {{ paymentOff }}
    </p>

    <!--
      Pay first. It is the only filled button on the page, and it is gone the
      moment the booking settles — there is nothing left to pay for.
    -->
    <button
      v-if="gateway?.status === 'ready' && !settled"
      type="button"
      class="payment-primary"
      @click="openCheckout"
    >
      Pay {{ order?.total }}
    </button>

    <div class="payment-secondary">
      <button type="button" class="payment-secondary-action" @click="router.push({ name: 'my-bookings' })">
        My bookings
      </button>
      <button type="button" class="payment-secondary-action" @click="router.push({ name: 'booking' })">
        Book another
      </button>
    </div>
  </section>
</template>
