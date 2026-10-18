<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import DatePicker from './DatePicker.vue'
import FacilityPicker from './FacilityPicker.vue'
import TimePicker from './TimePicker.vue'
import { useBookingForm } from '../composables/useBookingForm.js'
import { useCustomerStore } from '../stores/customer.js'
import { useVenuesStore } from '../stores/venues.js'
import '../styles/booking-form.css'

const props = defineProps({
  initialDate: { type: String, default: '' },
  initialFacility: { type: String, default: '' },
})

const form = useBookingForm(props.initialDate, props.initialFacility)
const venuesStore = useVenuesStore()
const customer = useCustomerStore()
const activePicker = ref(null)
// Signed in, the name and contact collapse to one line. This opens them back
// up when the booking is for someone else — a group, a friend — because the
// visit belongs to whoever plays, not to whoever holds the login.
const editingCustomer = ref(false)

// Booking is behind a login, so the account already knows who is booking and
// how to reach them. Asking again meant retyping the same details into a
// second form on the way to the same place — and getting it wrong here put the
// visit on an account it does not belong to, because the backend takes the
// owner from the token, not from this field.
const knownCustomer = computed(() => customer.isSignedIn && Boolean(customer.contact))

function fillFromAccount() {
  if (!customer.profile) return
  if (customer.displayName) form.customerName.value = customer.displayName
  if (customer.contact) form.customerContact.value = customer.contact
}

onMounted(() => {
  // Facilities come from the API; HomeView may already have loaded them.
  if (!venuesStore.facilities.length) venuesStore.load()
  fillFromAccount()
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
      <!--
        Signed in: one line saying who the booking is for, with a way to
        change it. Typing the same name and number a second time invited
        mistakes, and the backend takes the owner from the token anyway, so a
        typo here did not even do what it looked like it should.
      -->
      <div v-if="knownCustomer" class="booking-field">
        <span class="booking-label">Booking for</span>
        <div class="booking-known">
          <span class="booking-known-text">
            {{ customer.displayName }}
            <span v-if="customer.contact" class="booking-known-contact">· {{ customer.contact }}</span>
          </span>
          <button
            type="button"
            class="booking-known-edit"
            :aria-expanded="editingCustomer"
            @click="editingCustomer = !editingCustomer"
          >
            {{ editingCustomer ? 'Keep as is' : 'Change' }}
          </button>
        </div>
      </div>

      <div v-if="!knownCustomer || editingCustomer" class="booking-customer-fields">
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
      <label class="booking-field">
        <span class="booking-label">Promo code (optional)</span>
        <input
          v-model="form.promoCode.value"
          type="text"
          name="promo_code"
          autocomplete="off"
          autocapitalize="characters"
          spellcheck="false"
          placeholder="e.g. HEMAT20"
          class="booking-input booking-input-promo"
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

    <!-- The code's verdict, from the server's dry run. A refused code blocks
         Confirm outright: sending it would only bounce at booking time. -->
    <p v-if="form.promoChecking.value" class="booking-hint" role="status">Checking code…</p>
    <p
      v-else-if="form.promoError.value"
      class="booking-error"
      role="alert"
    >{{ form.promoError.value }}</p>
    <p
      v-else-if="form.promoRefused.value"
      class="booking-error"
      role="alert"
    >{{ form.promoResult.value.reason }}</p>
    <p
      v-else-if="form.promoAccepted.value"
      class="booking-hint booking-promo-ok"
      role="status"
    >{{ form.promoResult.value.code }} applied — {{ form.promoDiscount.value }} off</p>

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
      <div v-if="form.promoAccepted.value">
        <dt>Promo ({{ form.promoResult.value.code }})</dt>
        <dd class="booking-summary-discount">-{{ form.promoDiscount.value }}</dd>
      </div>
      <div>
        <dt>Total</dt>
        <dd class="booking-summary-total">{{ form.total.value }}</dd>
      </div>
    </dl>
  </section>
</template>
