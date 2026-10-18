<script setup>
import { computed, onMounted, ref } from 'vue'
import { cancelBookingGroup, errorDetail, errorStatus, fetchBookingHistory } from '../services/api.js'
import { getCustomerContact, setCustomerContact } from '../services/session.js'
import { useCustomerStore } from '../stores/customer.js'
import { formatHour, formatLongDate, toIsoDate } from '../utils/date.js'

const customer = useCustomerStore()
const contact = ref(getCustomerContact())
const visits = ref([])
const loading = ref(false)
const note = ref('')
const error = ref('')
const busyGroup = ref('')

// The history endpoint pages at 50 rows and reports the real total in
// `X-Total-Count`; without it a long booking history would quietly stop
// after the first page and look like the whole record.
const PAGE_SIZE = 50
const total = ref(0)
const hasMore = computed(() => visits.value.length < total.value)

const pad = (value) => String(value).padStart(2, '0')
const dateOf = (value) => String(value ?? '').slice(0, 10)
const timeOf = (value) => String(value ?? '').slice(11, 16)
const hourOf = (value) => Number(timeOf(value).slice(0, 2))

// One visit = one booking group; the rows are single booked hours.
const grouped = computed(() => {
  const byGroup = new Map()
  for (const row of visits.value) {
    const key = row.group_public_id ?? row.public_id
    const visit = byGroup.get(key)
    if (!visit) {
      byGroup.set(key, {
        id: key,
        date: dateOf(row.slot?.starts_at),
        startHour: hourOf(row.slot?.starts_at),
        endHour: hourOf(row.slot?.ends_at),
        hours: 1,
        facility: row.court?.name ?? '',
        venue: row.venue?.name ?? '',
        total: row.total ?? 0,
        status: row.status,
        paymentStatus: row.payment_status ?? 'unpaid',
        invoice: row.payment_invoice_number ?? '',
        cancellable: row.status !== 'cancelled' && dateOf(row.slot?.starts_at) >= toIsoDate(new Date()),
      })
      continue
    }
    visit.startHour = Math.min(visit.startHour, hourOf(row.slot?.starts_at))
    visit.endHour = Math.max(visit.endHour, hourOf(row.slot?.ends_at))
    visit.hours += 1
    visit.total += row.total ?? 0
    if (row.status === 'cancelled') visit.cancellable = false
    if (row.payment_invoice_number && !visit.invoice) visit.invoice = row.payment_invoice_number
  }
  return [...byGroup.values()].sort((a, b) => `${a.date}${a.startHour}`.localeCompare(`${b.date}${b.startHour}`))
})

function statusLabel(status) {
  if (status === 'confirmed') return 'Confirmed'
  if (status === 'cancelled') return 'Cancelled'
  return 'Pending'
}

function paymentLabel(status) {
  if (status === 'paid') return 'Paid'
  if (status === 'failed') return 'Payment failed'
  if (status === 'refunded') return 'Refunded'
  return 'Unpaid'
}

async function search() {
  const needle = contact.value.trim()
  // Signed in, the token already says who is asking — the contact is for
  // looking up visits made without an account.
  if (!customer.isSignedIn && needle.length < 3) {
    error.value = 'Enter the WhatsApp number or email you booked with.'
    return
  }
  loading.value = true
  error.value = ''
  note.value = ''
  try {
    const page = await fetchBookingHistory(needle || null, { limit: PAGE_SIZE, offset: 0 })
    visits.value = page.rows
    total.value = page.total
    if (needle) setCustomerContact(needle)
    if (!visits.value.length) {
      note.value = customer.isSignedIn
        ? 'No booking on this account yet.'
        : 'No booking found for that contact.'
    }
  } catch (err) {
    visits.value = []
    total.value = 0
    error.value = errorDetail(err, 'Could not load your bookings.')
  } finally {
    loading.value = false
  }
}

// One more page of the same contact's history, appended and de-duplicated by
// row id.
async function loadMore() {
  const needle = contact.value.trim()
  if ((!needle && !customer.isSignedIn) || loading.value || !hasMore.value) return
  loading.value = true
  error.value = ''
  try {
    const page = await fetchBookingHistory(needle || null, {
      limit: PAGE_SIZE,
      offset: visits.value.length,
    })
    const seen = new Set(visits.value.map((row) => row.public_id))
    visits.value = [...visits.value, ...page.rows.filter((row) => !seen.has(row.public_id))]
    total.value = page.total
  } catch (err) {
    error.value = errorDetail(err, 'Could not load the next page.')
  } finally {
    loading.value = false
  }
}

async function cancelVisit(visit) {
  busyGroup.value = visit.id
  error.value = ''
  note.value = ''
  try {
    // Signed in, the token proves ownership; otherwise the contact does.
    await cancelBookingGroup(visit.id, contact.value.trim())
    note.value = 'Visit cancelled. The hours are free again.'
    await search()
  } catch (err) {
    error.value =
      errorStatus(err) === 403
        ? customer.isSignedIn
          ? 'That visit does not belong to this account.'
          : 'That contact does not match this booking.'
        : errorDetail(err, 'Could not cancel the visit.')
  } finally {
    busyGroup.value = ''
  }
}

onMounted(async () => {
  // A signed-in customer's list needs nothing typed: the token is the query.
  if (customer.isSignedIn) {
    await search()
    return
  }
  if (contact.value.length >= 3) search()
})
</script>

<template>
  <section class="mx-auto max-w-2xl space-y-5">
    <h1 class="text-3xl font-bold tracking-tight text-gray-900">My bookings</h1>
    <p v-if="customer.isSignedIn" class="text-sm text-gray-600">
      Everything booked on your account. Cancel here too — no number to retype.
    </p>
    <p v-else class="text-sm text-gray-600">
      Look up the visits booked with your WhatsApp number or email. The same contact
      is what lets you cancel a visit. Have an account?
      <RouterLink
        :to="{ name: 'login', query: { as: 'customer' } }"
        class="font-semibold text-gray-900 underline"
        >Sign in</RouterLink
      >
      to skip this step.
    </p>

    <form class="flex flex-wrap items-end gap-2" @submit.prevent="search">
      <label class="flex min-w-0 flex-1 flex-col gap-1">
        <span class="text-xs font-semibold uppercase tracking-wide text-gray-500">WhatsApp / email</span>
        <input
          v-model="contact"
          type="text"
          name="customer_contact"
          placeholder="0812… or you@example.com"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900"
        />
      </label>
      <button
        type="submit"
        class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50"
        :disabled="loading"
      >
        {{ loading ? 'Searching…' : 'Find my bookings' }}
      </button>
    </form>

    <p v-if="error" class="text-sm text-red-600" role="alert">{{ error }}</p>
    <p v-if="note" class="text-sm text-gray-600" role="status">{{ note }}</p>

    <ul class="space-y-3">
      <li
        v-for="(visit, index) in grouped"
        :key="visit.id"
        class="stagger-item space-y-1 rounded-2xl border border-gray-300 bg-white p-4 tappable"
        :style="{ animationDelay: `${Math.min(index, 8) * 40}ms` }"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="font-semibold text-gray-900">{{ visit.facility }}</p>
            <p class="text-sm text-gray-600">{{ visit.venue }}</p>
          </div>
          <div class="text-right text-xs">
            <p class="font-semibold text-gray-700">{{ statusLabel(visit.status) }}</p>
            <p class="text-gray-500">{{ paymentLabel(visit.paymentStatus) }}</p>
          </div>
        </div>
        <p class="text-sm text-gray-600">{{ formatLongDate(visit.date) }}</p>
        <p class="text-sm text-gray-600">
          {{ formatHour(visit.startHour) }} - {{ formatHour(visit.endHour) }}
          ({{ visit.hours }} {{ visit.hours === 1 ? 'hour' : 'hours' }})
        </p>
        <p class="text-sm text-gray-600">Total: {{ visit.total }}</p>
        <p v-if="visit.invoice" class="text-xs text-gray-500">Invoice {{ visit.invoice }}</p>
        <p v-if="visit.paymentStatus === 'failed'" class="text-xs text-amber-700">
          The payment did not go through. Ask the venue what happens next — your hours are
          kept until the venue cancels or confirms this visit.
        </p>
        <button
          v-if="visit.cancellable"
          type="button"
          class="mt-2 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-semibold text-red-600 disabled:opacity-50"
          :disabled="busyGroup === visit.id"
          @click="cancelVisit(visit)"
        >
          {{ busyGroup === visit.id ? 'Cancelling…' : 'Cancel this visit' }}
        </button>
      </li>
    </ul>

    <!-- The history endpoint pages at 50; say how much is on screen so a long
         record is never mistaken for a short one. -->
    <div
      v-if="total > 0"
      class="flex items-center justify-between gap-3 text-sm text-gray-600"
    >
      <span role="status">
        Showing {{ visits.length }} of {{ total }} booked hours
      </span>
      <button
        v-if="hasMore"
        type="button"
        class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-900 disabled:opacity-50"
        :disabled="loading"
        @click="loadMore"
      >
        {{ loading ? 'Loading…' : 'Load more' }}
      </button>
    </div>
  </section>
</template>
