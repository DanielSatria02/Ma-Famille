<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { errorDetail, fetchAuditEvents } from '../services/api.js'
import '../styles/audit-trail.css'

// The change log, newest first. Every successful write under /v1/ lands here,
// so this is how a manager answers "who broke this and when".
const PAGE_SIZE = 25

const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const error = ref('')

// Free-text `actor` plus the two filters the backend understands directly.
const filters = ref({ entity_type: '', action: '', actor: '' })

const page = computed(() => Math.floor(offset.value / PAGE_SIZE) + 1)
const pages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasPrev = computed(() => offset.value > 0)
const hasNext = computed(() => offset.value + rows.value.length < total.value)

function describe(row) {
  const target = row.entity_public_id ? ` ${row.entity_public_id.slice(0, 8)}` : ''
  return `${row.entity_type}${target}`
}

function when(row) {
  // `2026-10-19T09:00:00` → `19 Oct 09:00`, shown in the reader's own clock.
  const d = new Date(row.created_at)
  if (Number.isNaN(d.getTime())) return row.created_at
  return d.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function activeFilters() {
  const out = { limit: PAGE_SIZE, offset: offset.value }
  for (const [key, value] of Object.entries(filters.value)) {
    const trimmed = value.trim()
    if (trimmed) out[key] = trimmed
  }
  return out
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchAuditEvents(activeFilters())
    rows.value = res.rows
    total.value = res.total
  } catch (err) {
    rows.value = []
    total.value = 0
    error.value = errorDetail(err, 'Could not load the audit trail.')
  } finally {
    loading.value = false
  }
}

function go(delta) {
  const next = offset.value + delta
  if (next < 0 || next >= total.value) return
  offset.value = next
  load()
}

// Any filter change restarts from the first page — the old offset would land
// past the end of the narrowed result.
watch(filters, () => {
  offset.value = 0
  load()
}, { deep: true })

onMounted(load)
</script>

<template>
  <section class="audit" aria-labelledby="audit-title">
    <div class="audit-head">
      <h2 id="audit-title" class="audit-title">Audit trail</h2>
      <p class="audit-count">{{ total }} events</p>
    </div>

    <div class="audit-filters">
      <label class="audit-field">
        <span class="audit-label">Entity</span>
        <select v-model="filters.entity_type" class="audit-input">
          <option value="">Any</option>
          <option value="venue">venue</option>
          <option value="court">court</option>
          <option value="booking">booking</option>
          <option value="payment">payment</option>
          <option value="promotion">promotion</option>
          <option value="session">session</option>
        </select>
      </label>

      <label class="audit-field">
        <span class="audit-label">Action</span>
        <input
          v-model="filters.action"
          type="text"
          autocomplete="off"
          spellcheck="false"
          placeholder="payment.refund"
          class="audit-input"
        />
      </label>

      <label class="audit-field">
        <span class="audit-label">Actor</span>
        <input
          v-model="filters.actor"
          type="text"
          autocomplete="off"
          spellcheck="false"
          placeholder="customer"
          class="audit-input"
        />
      </label>
    </div>

    <p v-if="error" class="audit-error" role="alert">{{ error }}</p>

    <div class="audit-panel">
      <p v-if="loading" class="audit-empty">Loading…</p>
      <p v-else-if="!rows.length" class="audit-empty">
        No events match. Clear a filter to widen the search.
      </p>

      <template v-else>
        <div v-for="(row, index) in rows" :key="row.public_id" class="audit-row">
          <div v-if="index > 0" class="audit-divider" role="separator" />
          <div class="audit-row-main">
            <div class="audit-row-info">
              <p class="audit-action">{{ row.action }}</p>
              <p class="audit-meta">
                {{ describe(row) }} · {{ row.actor }}
                <template v-if="row.detail"> · {{ row.detail }}</template>
              </p>
            </div>
            <time class="audit-when">{{ when(row) }}</time>
          </div>
        </div>
      </template>
    </div>

    <div class="audit-pager">
      <button
        type="button"
        class="audit-button"
        :disabled="!hasPrev || loading"
        @click="go(-PAGE_SIZE)"
      >
        ← Newer
      </button>
      <span class="audit-page">Page {{ page }} of {{ pages }}</span>
      <button
        type="button"
        class="audit-button"
        :disabled="!hasNext || loading"
        @click="go(PAGE_SIZE)"
      >
        Older →
      </button>
    </div>
  </section>
</template>
