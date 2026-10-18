<script setup>
import '../styles/todays-visitors.css'

// booking: { id, date, startTime, endTime, visitorName, venueName, status,
//            paymentStatus: 'unpaid'|'paid'|'partial'|'failed'|'refunded',
//            paymentNote: '', invoice, hours }
// date is an ISO date string (e.g. "2026-10-22").
const props = defineProps({
  booking: { type: Object, required: true },
  cancellable: { type: Boolean, default: false },
  manageable: { type: Boolean, default: false },
})

defineEmits(['cancel', 'confirm', 'markPaid', 'refund'])

function formatDate(date) {
  return new Date(`${date}T00:00`).toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

const paymentLabels = {
  paid: 'Paid',
  partial: 'Part paid',
  failed: 'Failed',
  refunded: 'Refunded',
  unpaid: 'Unpaid',
}
</script>

<template>
  <li class="visitor-card">
    <div class="visitor-info">
      <p class="visitor-schedule">
        {{ formatDate(booking.date) }} {{ booking.startTime }} - {{ booking.endTime }}
      </p>
      <p class="visitor-name">{{ booking.visitorName }}</p>
      <p class="visitor-venue">{{ booking.venueName }}</p>
      <p v-if="manageable" class="visitor-meta">
        <span class="visitor-badge" :class="`is-${booking.status}`">{{ booking.status }}</span>
        <span class="visitor-badge" :class="`is-pay-${booking.paymentStatus ?? 'unpaid'}`">
          {{ paymentLabels[booking.paymentStatus] ?? 'Unpaid' }}
        </span>
        <span v-if="booking.hours > 1" class="visitor-hours">{{ booking.hours }} hours</span>
      </p>
      <p v-if="manageable && booking.invoice" class="visitor-invoice">
        Invoice {{ booking.invoice }} · {{ booking.total }}
      </p>
      <p v-if="manageable && booking.paymentNote" class="visitor-note">
        {{ booking.paymentNote }}
      </p>
    </div>
    <div v-if="cancellable || manageable" class="visitor-actions">
      <button
        v-if="manageable && booking.status !== 'confirmed'"
        type="button"
        class="visitor-confirm"
        @click="$emit('confirm', booking)"
      >
        Confirm
      </button>
      <button
        v-if="manageable && booking.paymentStatus !== 'paid'"
        type="button"
        class="visitor-paid"
        @click="$emit('markPaid', booking)"
      >
        Mark paid
      </button>
      <button
        v-if="manageable && booking.refundable"
        type="button"
        class="visitor-refund"
        @click="$emit('refund', booking)"
      >
        Refund
      </button>
      <button v-if="cancellable" type="button" class="visitor-cancel" @click="$emit('cancel', booking)">
        Cancel
      </button>
    </div>
  </li>
</template>
