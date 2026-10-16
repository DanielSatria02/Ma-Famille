<script setup>
import { computed } from 'vue'
import '../styles/unavailable-notice.css'

// venues: [{ key, label, available }]
const props = defineProps({
  venues: { type: Array, required: true },
})

const unavailableNames = computed(() =>
  props.venues.filter((venue) => !venue.available).map((venue) => venue.label),
)

const message = computed(() => {
  const names = unavailableNames.value
  if (names.length === props.venues.length) return 'All venues are currently unavailable.'
  if (names.length === 1) return `${names[0]} is currently unavailable.`
  return `${names.slice(0, -1).join(', ')} and ${names.at(-1)} are currently unavailable.`
})
</script>

<template>
  <p v-if="unavailableNames.length" class="unavailable-notice" role="status">
    <span class="unavailable-notice-icon" aria-hidden="true">!</span>
    {{ message }}
  </p>
</template>
