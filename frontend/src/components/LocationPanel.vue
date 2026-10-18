<script setup>
import { computed, ref } from 'vue'
import mapOfJakartaCinere from '../assets/MapofJakartaCinere.svg'
import VenueFilters from './VenueFilters.vue'
import '../styles/location.css'

// The map art is static; the location list and the filters are live data.
// venues: [{ public_id, name, address, lat, lng }]
const props = defineProps({
  filterGroups: { type: Array, default: () => [] },
  filters: { type: Object, default: () => ({}) },
  venues: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:filters'])

const showLocations = ref(false)

const located = computed(() => props.venues.filter((venue) => venue.lat !== null && venue.lng !== null))
const mapsUrl = (venue) =>
  `https://www.google.com/maps/search/?api=1&query=${venue.lat},${venue.lng}`
</script>

<template>
  <section class="location-panel" aria-labelledby="location-panel-title">
    <h2 id="location-panel-title" class="location-panel-title">Map & Filter</h2>

    <div class="location-layout">
      <div class="location-preview">
        <div class="location-map-frame">
          <img
            :src="mapOfJakartaCinere"
            alt="Map showing the Jakarta and Cinere area"
            class="location-map-image"
          />
        </div>
        <button type="button" class="location-button" @click="showLocations = !showLocations">
          {{ showLocations ? 'Hide locations' : 'See all locations' }}
        </button>

        <ul v-if="showLocations" class="location-list">
          <li v-for="venue in venues" :key="venue.public_id" class="location-item">
            <p class="location-name">{{ venue.name }}</p>
            <p class="location-address">{{ venue.address }}</p>
            <a
              v-if="located.some((entry) => entry.public_id === venue.public_id)"
              :href="mapsUrl(venue)"
              target="_blank"
              rel="noopener"
              class="location-link"
            >
              Open in Maps
            </a>
          </li>
          <li v-if="!venues.length" class="location-item">No venues yet.</li>
        </ul>
      </div>

      <div class="location-filter">
        <VenueFilters
          :groups="filterGroups"
          :model-value="filters"
          @update:model-value="emit('update:filters', $event)"
        />
      </div>
    </div>
  </section>
</template>
