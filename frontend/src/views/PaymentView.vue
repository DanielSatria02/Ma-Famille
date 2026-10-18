<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCheckoutStore } from '../stores/checkout.js'
import { formatHour, formatLongDate } from '../utils/date.js'

const router = useRouter()
const checkout = useCheckoutStore()
const order = computed(() => checkout.pendingOrder)
const gateway = computed(() => checkout.gateway)

const notice = computed(() => {
  if (!order.value) return ''
  switch (gateway.value?.status) {
    case 'ready':
      return 'Your booking is held. Finish the payment to confirm it.'
    case 'unconfigured':
      return 'This server has no payment keys set yet, so the invoice could not be opened. Your booking stays pending until the manager confirms it.'
    case 'failed':
      return 'The payment session could not be opened. Your booking stays pending until the manager confirms it.'
    default:
      return ''
  }
})

function openCheckout() {
  if (gateway.value?.checkout_url) window.open(gateway.value.checkout_url, '_blank', 'noopener')
}
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

    <p v-if="notice" class="text-sm text-gray-600">{{ notice }}</p>

    <button
      v-if="gateway?.status === 'ready'"
      type="button"
      class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold"
      @click="openCheckout"
    >
      Open the payment page
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
