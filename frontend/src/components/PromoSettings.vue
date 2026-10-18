<script setup>
import { onMounted, ref } from 'vue'
import {
  createPromotion,
  deletePromotion,
  errorDetail,
  fetchPromotions,
  updatePromotion,
} from '../services/api.js'
import '../styles/promo-settings.css'

// Manager panel for promo codes: mint one, switch it off, remove it.
// Redemption itself happens at booking; this only shapes what the customer
// is allowed to redeem.
const rows = ref([])
const loading = ref(false)
const busy = ref('')
const error = ref('')
const notice = ref('')

const draft = ref(blank())
const formError = ref('')
const saving = ref(false)

function blank() {
  return { code: '', kind: 'percent', value: '', valid_from: '', valid_to: '', max_uses: '' }
}

// Codes are stored upper-case, so show them the way they will be redeemed.
// Normalise in the state, not the DOM: the template binds `:value`, so Vue
// writes the upper-cased text back on the next render.
function onCodeInput(event) {
  draft.value.code = event.target.value.toUpperCase()
}

function describe(row) {
  return row.kind === 'amount' ? `${row.value} off` : `${row.value}% off`
}

function windowLabel(row) {
  if (!row.valid_from && !row.valid_to) return 'no expiry'
  const from = row.valid_from ? row.valid_from.slice(0, 16).replace('T', ' ') : '…'
  const to = row.valid_to ? row.valid_to.slice(0, 16).replace('T', ' ') : '…'
  return `${from} → ${to}`
}

function usesLabel(row) {
  return row.max_uses === null ? `${row.used_count} used` : `${row.used_count}/${row.max_uses} used`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await fetchPromotions({ limit: 100 })
  } catch (err) {
    rows.value = []
    error.value = errorDetail(err, 'Could not load the promo codes.')
  } finally {
    loading.value = false
  }
}

function toIso(local) {
  // `datetime-local` gives `2026-12-31T23:59`; the API wants an ISO stamp.
  return local ? new Date(local).toISOString() : null
}

async function create() {
  formError.value = ''
  notice.value = ''
  const code = draft.value.code.trim()
  if (code.length < 3) {
    formError.value = 'A code needs at least 3 characters.'
    return
  }
  if (!(Number(draft.value.value) > 0)) {
    formError.value = 'Enter a value greater than zero.'
    return
  }
  if (draft.value.kind === 'percent' && Number(draft.value.value) > 100) {
    formError.value = 'A percent code cannot be over 100.'
    return
  }
  saving.value = true
  try {
    const made = await createPromotion({
      code,
      kind: draft.value.kind,
      value: Number(draft.value.value),
      valid_from: toIso(draft.value.valid_from),
      valid_to: toIso(draft.value.valid_to),
      max_uses: draft.value.max_uses === '' ? null : Number(draft.value.max_uses),
    })
    rows.value = [made, ...rows.value]
    draft.value = blank()
    notice.value = `${made.code} created.`
  } catch (err) {
    formError.value = errorDetail(err, 'Could not create the code.')
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  busy.value = row.public_id
  error.value = ''
  notice.value = ''
  try {
    const updated = await updatePromotion(row.public_id, { is_active: !row.is_active })
    rows.value = rows.value.map((entry) => (entry.public_id === row.public_id ? updated : entry))
    notice.value = updated.is_active ? `${updated.code} is active.` : `${updated.code} switched off.`
  } catch (err) {
    error.value = errorDetail(err, 'Could not update the code.')
  } finally {
    busy.value = ''
  }
}

async function remove(row) {
  busy.value = row.public_id
  error.value = ''
  notice.value = ''
  try {
    await deletePromotion(row.public_id)
    rows.value = rows.value.filter((entry) => entry.public_id !== row.public_id)
    notice.value = `${row.code} deleted.`
  } catch (err) {
    // A redeemed code is kept on purpose — it explains why a past booking was
    // cheaper, so the backend refuses and the manager deactivates instead.
    error.value = errorDetail(err, 'Could not delete the code.')
  } finally {
    busy.value = ''
  }
}

onMounted(load)
</script>

<template>
  <section class="promo-settings" aria-labelledby="promo-title">
    <h2 id="promo-title" class="promo-title">Promo codes</h2>

    <form class="promo-form" @submit.prevent="create">
      <div class="promo-form-grid">
        <label class="promo-field">
          <span class="promo-label">Code</span>
          <input
            :value="draft.code"
            type="text"
            maxlength="40"
            autocomplete="off"
            spellcheck="false"
            placeholder="HEMAT20"
            class="promo-input promo-input-code"
            required
            @input="onCodeInput"
          />
        </label>

        <label class="promo-field">
          <span class="promo-label">Type</span>
          <select v-model="draft.kind" class="promo-input">
            <option value="percent">% off</option>
            <option value="amount">amount off</option>
          </select>
        </label>

        <label class="promo-field">
          <span class="promo-label">{{ draft.kind === 'amount' ? 'Rupiah off' : 'Percent off' }}</span>
          <input
            v-model="draft.value"
            type="number"
            min="1"
            :max="draft.kind === 'percent' ? 100 : undefined"
            inputmode="numeric"
            placeholder="20"
            class="promo-input"
            required
          />
        </label>

        <label class="promo-field">
          <span class="promo-label">Max uses (optional)</span>
          <input
            v-model="draft.max_uses"
            type="number"
            min="1"
            step="1"
            inputmode="numeric"
            placeholder="unlimited"
            class="promo-input"
          />
        </label>

        <label class="promo-field">
          <span class="promo-label">Starts (optional)</span>
          <input v-model="draft.valid_from" type="datetime-local" class="promo-input" />
        </label>

        <label class="promo-field">
          <span class="promo-label">Ends (optional)</span>
          <input v-model="draft.valid_to" type="datetime-local" class="promo-input" />
        </label>
      </div>

      <p v-if="formError" class="promo-error" role="alert">{{ formError }}</p>

      <div class="promo-form-actions">
        <button type="submit" class="promo-button is-primary" :disabled="saving">
          {{ saving ? 'Creating…' : 'Create code' }}
        </button>
      </div>
    </form>

    <p v-if="notice" class="promo-notice" role="status">{{ notice }}</p>
    <p v-if="error" class="promo-error" role="alert">{{ error }}</p>

    <div class="promo-panel">
      <p v-if="loading" class="promo-empty">Loading codes…</p>
      <p v-else-if="!rows.length" class="promo-empty">
        No codes yet. Create one above; customers type it while booking.
      </p>

      <template v-else>
        <div v-for="(row, index) in rows" :key="row.public_id" class="promo-row">
          <div v-if="index > 0" class="promo-divider" role="separator" />
          <div class="promo-row-main">
            <div class="promo-row-info">
              <p class="promo-code">{{ row.code }}</p>
              <p class="promo-meta">
                {{ describe(row) }} · {{ windowLabel(row) }} · {{ usesLabel(row) }}
              </p>
            </div>
            <span
              class="promo-badge"
              :class="row.is_active ? 'is-on' : 'is-off'"
            >{{ row.is_active ? 'Active' : 'Off' }}</span>
            <div class="promo-row-actions">
              <button
                type="button"
                class="promo-button"
                :disabled="busy === row.public_id"
                @click="toggle(row)"
              >
                {{ row.is_active ? 'Switch off' : 'Switch on' }}
              </button>
              <button
                type="button"
                class="promo-button is-danger"
                :disabled="busy === row.public_id"
                @click="remove(row)"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>
