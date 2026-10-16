<script setup>
import { computed, ref } from 'vue'
import '../styles/pricing.css'

// items: [{ key, label, price }] where price is a number or null (null = unavailable for booking).
// Emits `update` with { key, price }.
const props = defineProps({
  items: { type: Array, required: true },
})

const emit = defineEmits(['update'])

const editingKey = ref(null)
const draftPrice = ref('')

const editingItem = computed(() => props.items.find((item) => item.key === editingKey.value))
const isDraftValid = computed(() => draftPrice.value !== '' && Number(draftPrice.value) > 0)

function startEdit(item) {
  editingKey.value = item.key
  draftPrice.value = item.price ?? ''
}

function cancelEdit() {
  editingKey.value = null
}

function save() {
  if (!isDraftValid.value) return
  emit('update', { key: editingKey.value, price: Number(draftPrice.value) })
  cancelEdit()
}

function reset(item) {
  emit('update', { key: item.key, price: null })
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
      <div class="pricing-editor-actions">
        <button type="submit" class="pricing-button is-primary" :disabled="!isDraftValid">Save</button>
        <button type="button" class="pricing-button" @click="cancelEdit">Cancel</button>
      </div>
    </form>
  </section>
</template>
