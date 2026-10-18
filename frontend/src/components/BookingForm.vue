<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import DatePicker from './DatePicker.vue'
import FacilityPicker from './FacilityPicker.vue'
import TimePicker from './TimePicker.vue'
import { useBookingForm } from '../composables/useBookingForm.js'
import { useVenuesStore } from '../stores/venues.js'
import '../styles/booking-form.css'

const props = defineProps({
  initialDate: { type: String, default: '' },
  initialFacility: { type: String, default: '' },
})

const form = useBookingForm(props.initialDate, props.initialFacility)
const venuesStore = useVenuesStore()
const activePicker = ref(null)

onMounted(() => {
  // Facilities come from the API; HomeView may already have loaded them.
  if (!venuesStore.facilities.length) venuesStore.load()
})

function toggle(picker) {
  activePicker.value = activePicker.value === picker ? null : picker
}

function close() {
  activePicker.value = null
}

function handleOutsideClick(event) {
  if (!event.target.closest('.picker-field')) close()
}

function handleKeydown(event) {
  if (event.key === 'Escape') close()
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <section class="booking-form" aria-label="Booking details">
    <div class="booking-form-bar">
      <FacilityPicker
        v-model="form.facilityKey.value"
        :options="form.facilityOptions.value"
        :open="activePicker === 'facility'"
        @toggle="toggle('facility')"
        @close="close"
      />
      <DatePicker
        :model-value="form.date.value"
        :open="activePicker === 'date'"
        @update:model-value="form.selectDate"
        @toggle="toggle('date')"
        @close="close"
      />
      <TimePicker
        :start-hour="form.startHour.value"
        :end-hour="form.endHour.value"
        :taken="form.taken.value"
        :open="activePicker === 'time'"
        @apply="({ start, end }) => form.selectTime(start, end)"
        @toggle="toggle('time')"
        @close="close"
      />
      <button
        type="button"
        class="booking-confirm"
        :disabled="!form.canConfirm.value || form.submitting.value"
        @click="form.confirm"
      >
        Confirm
      </button>
    </div>

    <div class="booking-customer">
      <label class="booking-field">
        <span class="booking-label">Name</span>
        <input
          v-model="form.customerName.value"
          type="text"
          name="customer_name"
          autocomplete="name"
          placeholder="Your name"
          class="booking-input"
        />
      </label>
      <label class="booking-field">
        <span class="booking-label">WhatsApp / email</span>
        <input
          v-model="form.customerContact.value"
          type="text"
          name="customer_contact"
          autocomplete="tel"
          placeholder="0812… or you@example.com"
          class="booking-input"
        />
      </label>
    </div>

    <p v-if="form.openWindow.value" class="booking-hint" role="status">{{ form.openWindow.value }}</p>
    <p v-if="form.facility.value && !form.isFacilityBookable.value" class="booking-error" role="alert">
      {{ form.facility.value.label }} is currently unavailable.
    </p>
    <p v-if="form.isClosed.value" class="booking-error" role="alert">
      The venue is closed on that date.
    </p>
    <p v-if="form.availabilityError.value" class="booking-error" role="alert">
      {{ form.availabilityError.value }}
    </p>
    <p v-if="form.timeNotice.value" class="booking-error" role="alert">{{ form.timeNotice.value }}</p>
    <p v-if="form.submitError.value" class="booking-error" role="alert">{{ form.submitError.value }}</p>

    <dl v-if="form.facility.value && form.hasTime.value && form.isFacilityBookable.value" class="booking-summary">
      <div>
        <dt>Rate</dt>
        <dd>{{ form.hourlyRate.value }} /hour</dd>
      </div>
      <div>
        <dt>Duration</dt>
        <dd>{{ form.hours.value }} {{ form.hours.value === 1 ? 'hour' : 'hours' }}</dd>
      </div>
      <div>
        <dt>Total</dt>
        <dd class="booking-summary-total">{{ form.total.value }}</dd>
      </div>
    </dl>
  </section>
</template>
