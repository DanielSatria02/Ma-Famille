<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useCheckoutStore } from '../stores/checkout.js'
import { formatHour, formatLongDate } from '../utils/date.js'

const router = useRouter()
const checkout = useCheckoutStore()
const order = computed(() => checkout.pendingOrder)
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
    </div>
    <p v-else class="text-gray-600">There is nothing to pay for yet.</p>

    <p class="text-sm text-gray-600">The payment gateway has not been connected yet.</p>
    <button
      type="button"
      class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold"
      @click="router.push({ name: 'booking' })"
    >
      Back to booking
    </button>
  </section>
</template>
