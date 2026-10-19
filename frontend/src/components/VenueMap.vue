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

// Where the map opens.
//
// Fitting the bounds to every club is what the obvious version does, and it is
// useless here: the clubs are spread over Greater Jakarta, so fitting them all
// zooms out until the map is a grey square with twenty-five dots and no
// streets. A map that shows nothing you can act on is worse than no map.
//
// So the map opens on the densest cluster — the district with the most clubs —
// and the rest is one drag away. Everything is still pinned, so nothing is
// hidden; this only decides where the viewport starts.
const view = computed(() => {
  const points = placed.value
  if (!points.length) return null
  if (points.length === 1) return { center: [points[0].lat, points[0].lng], zoom: 15 }

  // Half a degree is about 55km, which is small enough to keep one city's
  // venues together and large enough not to split Jakarta across four buckets.
  // Finer than this and the densest cluster is a single venue, so the map opens
  // on one address and never shows the other seventeen.
  const buckets = new Map()
  for (const point of points) {
    const key = `${Math.round(point.lat * 2)}:${Math.round(point.lng * 2)}`
    const bucket = buckets.get(key) ?? []
    bucket.push(point)
    buckets.set(key, bucket)
  }
  const densest = [...buckets.values()].sort((a, b) => b.length - a.length)[0]

  const lats = densest.map((point) => point.lat)
  const lngs = densest.map((point) => point.lng)
  const center = [
    (Math.min(...lats) + Math.max(...lats)) / 2,
    (Math.min(...lngs) + Math.max(...lngs)) / 2,
  ]
  // One venue, or several in a line, gets street level. A spread-out cluster
  // pulls back rather than putting four markers on top of each other.
  const span = Math.max(Math.max(...lats) - Math.min(...lats), Math.max(...lngs) - Math.min(...lngs))
  const zoom = span < 0.02 ? 14 : 12
  return { center, zoom }
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

// Leaflet measures its container once, when the map is created, and never asks
// again. This panel sits below the venue grid and the venues arrive after it, so
// on a first visit the map is built against a box that has not been laid out
// yet — and a box Leaflet measured as empty gets one tile, whatever the viewport
// is.
function measure() {
  if (!map.value) return
  map.value.invalidateSize({ animate: false, pan: false })
  fitToVenues()
}

function fitToVenues() {
  if (!leaflet || !map.value || !markers.length) return
  // The same view the map opens at. fitBounds here would undo the clustering
  // above and zoom out to fit a venue in Medan with one in Surabaya.
  const target = view.value
  if (!target) return
  // No animation. The map has nothing to animate from — it is being told where
  // to be, not moved — and a panned setView leaves the old tiles up until it
  // finishes, which on a slow connection is a second of the wrong city.
  map.value.setView(target.center, target.zoom, { animate: false })
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

  // Leaflet reads its container once, at the moment the map is made, and never
  // asks again. This panel is below the venue grid and starts empty — the
  // container is hidden until venues arrive — so at that moment it has no box
  // at all, and a map sized against nothing draws exactly one tile however wide
  // the window is.
  //
  // The container can stay at nothing for a while: the stylesheet arrives, the
  // venues come back, the element stops being hidden. None of those are visible
  // from here, so the box is watched for the life of the component and every
  // change re-measures and re-fits.
  observer = new ResizeObserver(measure)
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
    measure()
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