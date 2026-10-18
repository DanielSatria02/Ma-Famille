<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { directionsUrl, hasCoordinates } from '../utils/maps.js'
// Leaflet's own stylesheet, and it is not optional. Without it the tile images
// are ordinary <img> elements at their natural size, the panes have no absolute
// positioning, and the map container has no height or overflow of its own — the
// tiles then spill across the rest of the page instead of tiling inside the box.
// The JavaScript half works either way, which is what makes it look like a tile
// problem rather than a missing one.
import 'leaflet/dist/leaflet.css'
import '../styles/venue-map.css'

// Where the venue is, on a map drawn by OpenStreetMap.
//
// The tiles come from openstreetmap.org, which needs no key and no billing
// account, so the map works on the web build and on a laptop with no config at
// all. What Leaflet is for here is the map itself, the marker and the panning;
// the turn-by-turn is left to whichever navigation app the visitor already has,
// which is a better answer than one we could write here.
//
// Leaflet is loaded on demand: it is 145KB of JavaScript and a visitor who never
// scrolls down to the map should not pay for it.

const props = defineProps({
  venues: { type: Array, required: true },
  activePublicId: { type: String, default: '' },
})

const emit = defineEmits(['select'])

const container = ref(null)
const map = shallowRef(null)
const loadFailed = ref(false)
let leaflet = null
let markers = []
let markersLayer = null
let observer = null

const placed = computed(() =>
  props.venues.filter(hasCoordinates).map((venue) => ({
    publicId: venue.public_id,
    name: venue.name,
    address: venue.address ?? '',
    lat: venue.lat,
    lng: venue.lng,
  })),
)

// Zoom depends on how spread out the venues are: one venue reads fine at street
// level, several within a kilometre need to pull back or the markers land on top
// of each other.
const view = computed(() => {
  const points = placed.value
  if (!points.length) return null
  if (points.length === 1) return { center: [points[0].lat, points[0].lng], zoom: 15 }

  const lats = points.map((point) => point.lat)
  const lngs = points.map((point) => point.lng)
  return {
    center: [
      (Math.min(...lats) + Math.max(...lats)) / 2,
      (Math.min(...lngs) + Math.max(...lngs)) / 2,
    ],
    zoom: 13,
  }
})

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ESCAPES[char])

async function ensureLeaflet() {
  if (leaflet || loadFailed.value) return leaflet
  try {
    const loaded = await import('leaflet')
    leaflet = loaded.default ?? loaded
    return leaflet
  } catch {
    loadFailed.value = true
    return null
  }
}

// Leaflet's own marker is a PNG fetched from a path inside the package, which is
// not there once the package is bundled. A divIcon draws the pin in CSS instead,
// so nothing extra is fetched and it follows the app's own colours.
function pinIcon(isActive) {
  return leaflet.divIcon({
    className: 'venue-map-pin-wrapper',
    html: `<span class="venue-map-pin${isActive ? ' is-active' : ''}"></span>`,
    iconSize: [22, 30],
    iconAnchor: [11, 30],
    popupAnchor: [0, -28],
  })
}

function popupHtml(venue) {
  return (
    `<div class="venue-map-popup">` +
    `<p class="venue-map-popup-name">${escapeHtml(venue.name)}</p>` +
    (venue.address ? `<p class="venue-map-popup-address">${escapeHtml(venue.address)}</p>` : '') +
    `<a class="venue-map-popup-go" href="${directionsUrl(venue)}" target="_blank" rel="noopener">` +
    `Open in Google Maps</a>` +
    `</div>`
  )
}

function drawMarkers() {
  if (!leaflet || !map.value || !markersLayer) return
  markersLayer.clearLayers()
  markers = placed.value.map((venue) => {
    const marker = leaflet.marker([venue.lat, venue.lng], {
      icon: pinIcon(venue.publicId === props.activePublicId),
      title: venue.name,
      alt: venue.name,
      keyboard: true,
    })
    marker.on('click', () => emit('select', venue.publicId))
    marker.bindPopup(popupHtml(venue), { closeButton: true, maxWidth: 260 })
    marker.addTo(markersLayer)
    return marker
  })
}

function fitToVenues() {
  if (!leaflet || !map.value || !markers.length) return
  if (markers.length === 1) {
    const only = view.value
    map.value.setView(only.center, only.zoom)
    return
  }
  map.value.fitBounds(
    leaflet.latLngBounds(markers.map((marker) => marker.getLatLng())),
    { padding: [28, 28], maxZoom: 15 },
  )
}

onMounted(async () => {
  const ready = await ensureLeaflet()
  if (!ready || !container.value) return

  map.value = leaflet.map(container.value, {
    // The wheel scrolls the page on a laptop, which is what someone reading the
    // page expects; the map zooms when it is dragged or double-clicked.
    scrollWheelZoom: false,
    // Leaflet's zoom animation holds the old tiles until it finishes. On a slow
    // phone that is a second of the old view after every tap, and if the
    // animation is interrupted the map can be left waiting on tiles that never
    // arrive. Nothing here is worth a transition.
    zoomAnimation: false,
    fadeAnimation: false,
    markerZoomAnimation: false,
  })

  leaflet
    .tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    })
    .addTo(map.value)

  markersLayer = leaflet.layerGroup().addTo(map.value)
  drawMarkers()
  fitToVenues()

  // Leaflet works out which tiles to draw from whatever size its container had
  // at the moment of the call, and it never asks again on its own. This panel
  // sits below the venue grid, so on a first visit it has not been laid out
  // when the map is made, and the map sizes itself against an empty box: one
  // tile, pinned over the middle of the Atlantic.
  //
  // Guessing when that happens is a losing game — the panel can be laid out
  // after a font loads, after the venue list arrives, after a scrollbar appears.
  // So the box is watched, and every time it changes Leaflet is told to measure
  // itself again.
  observer = new ResizeObserver(() => {
    map.value?.invalidateSize({ animate: false })
  })
  observer.observe(container.value)
})

watch(
  () => [props.venues, props.activePublicId],
  () => {
    // The venues arrive after this component mounts — the parent loads them —
    // so the first draw has nothing to put on the map and the map is still
    // sitting at the default view, which is the middle of the Atlantic.
    // Measuring and fitting is what puts the pins in the viewport and the tiles
    // on screen; a redraw on its own leaves both off.
    if (!map.value) return
    drawMarkers()
    map.value.invalidateSize({ animate: false })
    fitToVenues()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  map.value?.remove()
  map.value = null
  markers = []
})
</script>

<template>
  <div class="venue-map">
    <div class="venue-map-head">
      <h2 class="venue-map-title">Where it is</h2>
      <p v-if="placed.length" class="venue-map-count">
        {{ placed.length }} {{ placed.length === 1 ? 'place' : 'places' }}
      </p>
    </div>

    <p v-if="loadFailed" class="venue-map-note" role="status">
      The map could not be loaded. The addresses are below.
    </p>

    <div v-show="placed.length && !loadFailed" ref="container" class="venue-map-canvas" />

    <p v-if="!placed.length" class="venue-map-note">
      {{
        venues.length
          ? 'No coordinates are set for this venue yet, so there is nothing to put on a map.'
          : 'No venues to show yet.'
      }}
    </p>

    <!-- The addresses, always. A map is a picture; a list of them is a fact, and
         it still works with no network and with the map blocked. -->
    <ul v-if="placed.length" class="venue-map-list">
      <li v-for="venue in placed" :key="venue.publicId" class="venue-map-list-item">
        <button
          type="button"
          class="venue-map-list-name"
          :class="{ 'is-active': venue.publicId === activePublicId }"
          @click="emit('select', venue.publicId)"
        >
          {{ venue.name }}
        </button>
        <span v-if="venue.address" class="venue-map-list-address">{{ venue.address }}</span>
        <a
          v-if="venue.address"
          class="venue-map-list-go"
          :href="directionsUrl(venue)"
          target="_blank"
          rel="noopener"
        >
          Directions
        </a>
      </li>
    </ul>
  </div>
</template>