<script setup>
import { computed, onMounted, ref } from 'vue'
import { errorDetail, fetchOccupancy } from '../services/api.js'
import { addDays, toIsoDate } from '../utils/date.js'
import '../styles/occupancy-chart.css'

const DAYS = 7
const props = defineProps({
  days: { type: Number, default: DAYS },
})

const points = ref([])
const error = ref('')
const loading = ref(false)

const best = computed(() =>
  points.value.reduce((top, point) => (point.occupancy_rate > (top?.occupancy_rate ?? -1) ? point : top), null),
)
const average = computed(() => {
  if (!points.value.length) return 0
  return points.value.reduce((sum, point) => sum + point.occupancy_rate, 0) / points.value.length
})

function percent(rate) {
  return `${Math.round((rate ?? 0) * 100)}%`
}

function barHeight(rate) {
  // Minimum stub so an empty day is still visible next to a busy one.
  return `${Math.max((rate ?? 0) * 100, 2)}%`
}

function shortLabel(day) {
  return new Date(`${day}T00:00`).toLocaleDateString('en-GB', { weekday: 'short' })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const today = new Date()
    points.value = await fetchOccupancy(
      toIsoDate(today),
      toIsoDate(addDays(today, props.days - 1)),
    )
  } catch (err) {
    points.value = []
    error.value = errorDetail(err, 'Could not load the occupancy.')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="occupancy" aria-labelledby="occupancy-title">
    <h2 id="occupancy-title" class="occupancy-title">Occupancy · next {{ props.days }} days</h2>

    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
    <p v-else-if="loading && !points.length" class="occupancy-line">Loading…</p>
    <p v-else-if="!points.length" class="occupancy-line">No slots generated for the coming week.</p>

    <template v-else>
      <ol class="occupancy-bars">
        <li v-for="point in points" :key="point.day" class="occupancy-bar">
          <span class="occupancy-value">{{ percent(point.occupancy_rate) }}</span>
          <span class="occupancy-track">
            <span class="occupancy-fill" :style="{ height: barHeight(point.occupancy_rate) }" />
          </span>
          <span class="occupancy-label">{{ shortLabel(point.day) }}</span>
          <span class="occupancy-detail">{{ point.booked_slots }}/{{ point.total_slots }}</span>
        </li>
      </ol>
      <p class="occupancy-line">
        Average {{ percent(average) }}<template v-if="best"> · busiest {{ shortLabel(best.day) }} ({{ percent(best.occupancy_rate) }})</template>
      </p>
    </template>
  </section>
</template>
