<script setup>
import { computed, onMounted, ref } from 'vue'
import { dispatchNotifications, errorDetail, fetchNotifications } from '../services/api.js'
import '../styles/guest-messages.css'

const messages = ref([])
const result = ref(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')

const queued = computed(() => messages.value.filter((row) => row.status === 'queued').length)
const labels = {
  pending: 'received',
  confirmed: 'confirmed',
  cancelled: 'cancelled',
}

function when(value) {
  const stamp = new Date(`${String(value).replace('Z', '')}Z`)
  if (Number.isNaN(stamp.getTime())) return ''
  return stamp.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    messages.value = await fetchNotifications({ limit: 8 })
  } catch (err) {
    messages.value = []
    error.value = errorDetail(err, 'Could not load the guest messages.')
  } finally {
    loading.value = false
  }
}

async function send() {
  busy.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await dispatchNotifications()
    await load()
  } catch (err) {
    error.value = errorDetail(err, 'Could not send the queued messages.')
  } finally {
    busy.value = false
  }
}

function summary(dispatch) {
  const parts = []
  if (dispatch.sent) parts.push(`${dispatch.sent} sent via ${dispatch.transport}`)
  if (dispatch.logged) {
    parts.push(`${dispatch.logged} recorded (no provider configured, nothing delivered)`)
  }
  if (dispatch.failed) parts.push(`${dispatch.failed} failed`)
  if (dispatch.still_queued) parts.push(`${dispatch.still_queued} still queued`)
  return parts.length ? parts.join(' · ') : 'Nothing was waiting.'
}

onMounted(load)
</script>

<template>
  <section class="guest-messages" aria-labelledby="guest-messages-title">
    <h2 id="guest-messages-title" class="guest-messages-title">Guest Messages</h2>
    <p class="guest-messages-line">
      One message per visit, written when the booking changes. {{ queued }} waiting to go out.
    </p>

    <ul v-if="messages.length" class="guest-list">
      <li v-for="message in messages" :key="message.public_id" class="guest-item">
        <div class="guest-info">
          <p class="guest-subject">{{ message.subject }}</p>
          <p class="guest-meta">
            {{ message.recipient }} · {{ message.channel }} · {{ when(message.created_at) }}
            <template v-if="message.error"> · {{ message.error }}</template>
          </p>
        </div>
        <span class="guest-badge" :class="`is-${message.status}`">
          {{ message.status }}
        </span>
      </li>
    </ul>
    <p v-else-if="!loading" class="guest-messages-line">No messages yet.</p>

    <button
      type="button"
      class="guest-button"
      :disabled="busy || !queued"
      @click="send"
    >
      {{ busy ? 'Sending…' : `Send ${queued || ''} queued message(s)` }}
    </button>
    <p v-if="result" class="guest-messages-line" role="status">{{ summary(result) }}</p>
    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
  </section>
</template>
