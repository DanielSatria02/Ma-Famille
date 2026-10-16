<script setup>
// A labelled trigger button with a popover panel (default slot) shown while `open`.
defineProps({
  label: { type: String, required: true },
  value: { type: String, default: '' },
  open: { type: Boolean, default: false },
  panelClass: { type: String, default: '' },
})

defineEmits(['toggle'])
</script>

<template>
  <div class="picker-field">
    <button
      type="button"
      class="picker-trigger"
      :class="{ 'is-open': open }"
      aria-haspopup="true"
      :aria-expanded="open"
      @click="$emit('toggle')"
    >
      <span class="picker-trigger-label">{{ label }}</span>
      <span class="picker-trigger-value">{{ value || 'Select' }}</span>
    </button>
    <div v-if="open" class="picker-panel" :class="panelClass">
      <slot />
    </div>
  </div>
</template>
