<script setup>
import '../styles/venue-status.css'

// venues: [{ key, label, available, locked }]; locked disables the toggle (e.g. no price set yet).
// Emits `toggle` with { key, available }.
defineProps({
  venues: { type: Array, required: true },
})

defineEmits(['toggle'])
</script>

<template>
  <section class="venue-status" aria-labelledby="venue-status-title">
    <h2 id="venue-status-title" class="venue-status-title">Venue Status</h2>

    <ul class="venue-status-list">
      <li v-for="venue in venues" :key="venue.key" class="venue-status-card">
        <div class="venue-status-info">
          <p class="venue-status-name">{{ venue.label }}</p>
          <p class="venue-status-state" :class="venue.available ? 'is-available' : 'is-unavailable'">
            {{ venue.available ? 'Available' : 'Unavailable' }}
          </p>
          <p v-if="venue.locked" class="venue-status-hint">Set a price to make it available.</p>
        </div>
        <button
          type="button"
          role="switch"
          class="venue-switch"
          :class="{ 'is-on': venue.available }"
          :aria-checked="venue.available"
          :aria-label="`${venue.label} availability`"
          :disabled="venue.locked"
          @click="$emit('toggle', { key: venue.key, available: !venue.available })"
        >
          <span class="venue-switch-thumb" />
        </button>
      </li>
    </ul>
  </section>
</template>
