<script setup>
import { computed, ref } from 'vue'
import '../styles/pricing.css'

// items: [{ key, label, price, peak: { price, start, end } }] where price is a
// number or null (null = unavailable for booking). `peak` is the optional
// premium window; peak.price null means no peak rate is configured.
// Emits `update` with { key, price, peak }.
const props = defineProps({
  items: { type: Array, required: true },
})

const emit = defineEmits(['update'])

const editingKey = ref(null)
const draftPrice = ref('')
const draftPeakPrice = ref('')
const draftPeakStart = ref('')
const draftPeakEnd = ref('')

const editingItem = computed(() => props.items.find((item) => item.key === editingKey.value))
const isDraftValid = computed(() => draftPrice.value !== '' && Number(draftPrice.value) > 0)

// Backend needs the peak window complete or absent, so refuse a half-filled
// block here instead of letting the PATCH bounce.
const peakTouched = computed(
  () => draftPeakPrice.value !== '' || draftPeakStart.value !== '' || draftPeakEnd.value !== '',
)
const peakComplete = computed(
  () => draftPeakPrice.value !== '' && draftPeakStart.value !== '' && draftPeakEnd.value !== '',
)
const peakError = computed(() => {
  if (!peakTouched.value || peakComplete.value) return ''
  return 'Peak price, start hour and end hour are needed together.'
})
const peakWindowValid = computed(() => {
  if (!peakComplete.value) return true
  const start = Number(draftPeakStart.value)
  const end = Number(draftPeakEnd.value)
  return (
    Number(draftPeakPrice.value) > 0 &&
    Number.isInteger(start) &&
    Number.isInteger(end) &&
    start >= 0 &&
    start <= 23 &&
    end >= 1 &&
    end <= 24 &&
    start < end
  )
})
const peakWindowError = computed(() => {
  if (!peakComplete.value || peakWindowValid.value) return ''
  return 'Use whole hours: start 0–23, end 1–24, and start before end.'
})
const canSave = computed(() => isDraftValid.value && !peakError.value && peakWindowValid.value)

function startEdit(item) {
  editingKey.value = item.key
  draftPrice.value = item.price ?? ''
  draftPeakPrice.value = item.peak?.price ?? ''
  draftPeakStart.value = item.peak?.start ?? ''
  draftPeakEnd.value = item.peak?.end ?? ''
}

function cancelEdit() {
  editingKey.value = null
}

function save() {
  if (!canSave.value) return
  // Cleared block goes out as three nulls, which the backend reads as
  // "no peak rate"; a filled one always travels as all three.
  const peak = peakComplete.value
    ? {
        price: Number(draftPeakPrice.value),
        start: Number(draftPeakStart.value),
        end: Number(draftPeakEnd.value),
      }
    : { price: null, start: null, end: null }
  emit('update', { key: editingKey.value, price: Number(draftPrice.value), peak })
  cancelEdit()
}

function reset(item) {
  emit('update', { key: item.key, price: null, peak: { price: null, start: null, end: null } })
  if (editingKey.value === item.key) cancelEdit()
}
</script>

<template>
  <section class="pricing" aria-labelledby="pricing-title">
    <h2 id="pricing-title" class="pricing-title">Pricing</h2>

    <div class="pricing-panel">
      <template v-for="(item, index) in items" :key="item.key">
        <div v-if="index > 0" class="pricing-divider" role="separator" />
        <div class="pricing-row">
          <div class="pricing-info">
            <p class="pricing-name">Current {{ item.label }} Price</p>
            <p v-if="item.price !== null" class="pricing-value">Current price: {{ item.price }} /hour</p>
            <p v-else class="pricing-value is-unset">Current price: not set (unavailable for booking)</p>
            <p v-if="item.peak?.price !== null && item.peak?.price !== undefined" class="pricing-value pricing-peak">
              Peak: {{ item.peak.price }} /hour from {{ item.peak.start }}:00–{{ item.peak.end }}:00
            </p>
            <p v-else class="pricing-value pricing-peak is-unset">Peak rate: not set</p>
          </div>
          <div class="pricing-actions">
            <button type="button" class="pricing-button" @click="startEdit(item)">Edit</button>
            <button type="button" class="pricing-button is-danger" @click="reset(item)">Reset</button>
          </div>
        </div>
      </template>
    </div>

    <form v-if="editingItem" class="pricing-panel pricing-editor" @submit.prevent="save">
      <h3 class="pricing-editor-title">Edit {{ editingItem.label }} Price</h3>
      <label class="pricing-field">
        <span class="pricing-label">New price (per hour)</span>
        <input
          v-model="draftPrice"
          type="number"
          min="1"
          step="any"
          inputmode="decimal"
          class="pricing-input"
          required
        />
      </label>

      <fieldset class="pricing-peak">
        <legend class="pricing-label">Peak hours (optional)</legend>
        <p class="pricing-peak-hint">
          A premium rate for one window of the day. Leave all three empty for no peak rate.
        </p>
        <div class="pricing-peak-grid">
          <label class="pricing-field">
            <span class="pricing-label">Peak price (/hour)</span>
            <input
              v-model="draftPeakPrice"
              type="number"
              min="1"
              step="any"
              inputmode="decimal"
              placeholder="e.g. 150000"
              class="pricing-input"
            />
          </label>
          <label class="pricing-field">
            <span class="pricing-label">From (hour)</span>
            <input
              v-model="draftPeakStart"
              type="number"
              min="0"
              max="23"
              step="1"
              inputmode="numeric"
              placeholder="17"
              class="pricing-input"
            />
          </label>
          <label class="pricing-field">
            <span class="pricing-label">Until (hour)</span>
            <input
              v-model="draftPeakEnd"
              type="number"
              min="1"
              max="24"
              step="1"
              inputmode="numeric"
              placeholder="22"
              class="pricing-input"
            />
          </label>
        </div>
        <p v-if="peakError" class="pricing-peak-error" role="alert">{{ peakError }}</p>
        <p v-else-if="peakWindowError" class="pricing-peak-error" role="alert">{{ peakWindowError }}</p>
      </fieldset>

      <div class="pricing-editor-actions">
        <button type="submit" class="pricing-button is-primary" :disabled="!canSave">Save</button>
        <button type="button" class="pricing-button" @click="cancelEdit">Cancel</button>
      </div>
    </form>
  </section>
</template>
