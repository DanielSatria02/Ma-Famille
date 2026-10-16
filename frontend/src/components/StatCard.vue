<script setup>
import '../styles/stat-card.css'

defineProps({
  value: { type: Number, default: 0 },
  label: { type: String, required: true },
})
</script>

<template>
  <div class="stat-card">
    <span class="stat-icon" aria-hidden="true">
      <slot name="icon" />
    </span>
    <div class="stat-content">
      <p class="stat-value">{{ value }}</p>
      <p class="stat-label">{{ label }}</p>
    </div>
  </div>
</template>
