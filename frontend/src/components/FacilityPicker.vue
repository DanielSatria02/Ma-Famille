<script setup>
import PickerField from './PickerField.vue'

// options: [{ key, label, bookable }]
defineProps({
  options: { type: Array, required: true },
  modelValue: { type: String, default: '' },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'toggle', 'close'])

function choose(option) {
  if (!option.bookable) return
  emit('update:modelValue', option.key)
  emit('close')
}
</script>

<template>
  <PickerField
    label="Facility"
    :value="options.find((option) => option.key === modelValue)?.label"
    :open="open"
    @toggle="emit('toggle')"
  >
    <ul class="facility-list" role="listbox" aria-label="Facility">
      <li v-for="option in options" :key="option.key">
        <button
          type="button"
          role="option"
          class="facility-option"
          :class="{ 'is-selected': option.key === modelValue }"
          :aria-selected="option.key === modelValue"
          :disabled="!option.bookable"
          @click="choose(option)"
        >
          <span>{{ option.label }}</span>
          <span v-if="!option.bookable" class="facility-option-note">Unavailable</span>
        </button>
      </li>
    </ul>
  </PickerField>
</template>
