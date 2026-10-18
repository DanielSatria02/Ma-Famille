<script setup>
import { computed, ref } from 'vue'
import {
  errorDetail,
  errorStatus,
  fetchRatingSummary,
  fetchReviews,
  writeReview,
} from '../services/api.js'
import { getCustomerContact } from '../services/session.js'
import { useCustomerStore } from '../stores/customer.js'
import { formatLongDate } from '../utils/date.js'
import '../styles/reviews.css'

// What other visitors thought of a venue, and a way to leave an opinion.
//
// The form is here rather than on the booking page because that is when it
// means something: the backend refuses a rating from anyone whose visit has
// not happened, so the only honest time to ask is after one.

const props = defineProps({
  venuePublicId: { type: String, required: true },
  venueName: { type: String, default: '' },
})

const customer = useCustomerStore()

const summary = ref(null)
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')

const stars = ref(0)
const comment = ref('')
const contact = ref(getCustomerContact())
const sending = ref(false)
const notice = ref('')
const sendError = ref('')

// `mine` marks the visitor's own rating, which they may change but not add to.
const mine = computed(() => rows.value.find((row) => row.mine) ?? null)

const PAGE_SIZE = 10
const hasMore = computed(() => rows.value.length < total.value)

const starsOf = (value) => Math.round(value ?? 0)

function distributionBar(count) {
  // Not a percentage of the page: of the ratings this venue has, so a venue
  // with three reviews does not draw three full bars.
  const all = summary.value?.count ?? 0
  if (!all || !count) return '0%'
  return `${Math.round((count / all) * 100)}%`
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    // Both are asked at once: a page that shows the average without the words
    // next to it reads as a rating nobody stands behind.
    const [summaryResult, page] = await Promise.all([
      fetchRatingSummary(props.venuePublicId),
      fetchReviews(props.venuePublicId, { limit: PAGE_SIZE }),
    ])
    summary.value = summaryResult
    rows.value = page.rows
    total.value = page.total
    if (mine.value) {
      // Open editing the rating they already left, not a blank form that would
      // silently replace it.
      stars.value = mine.value.rating
      comment.value = mine.value.comment ?? ''
    }
  } catch (err) {
    loadError.value = errorDetail(err, 'Could not load the reviews.')
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!hasMore.value || loading.value) return
  loading.value = true
  try {
    const page = await fetchReviews(props.venuePublicId, {
      limit: PAGE_SIZE,
      offset: rows.value.length,
    })
    const seen = new Set(rows.value.map((row) => row.public_id))
    rows.value = [...rows.value, ...page.rows.filter((row) => !seen.has(row.public_id))]
    total.value = page.total
  } catch (err) {
    loadError.value = errorDetail(err, 'Could not load the next page.')
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!stars.value || sending.value) return
  sending.value = true
  notice.value = ''
  sendError.value = ''
  try {
    const saved = await writeReview(props.venuePublicId, {
      rating: stars.value,
      comment: comment.value.trim(),
      customerContact: customer.isSignedIn ? '' : contact.value.trim(),
    })
    notice.value = mine.value ? 'Your rating was updated.' : 'Thanks — your rating is up.'
    // Re-read rather than patching the row: the server decides which row this
    // was, and the average has moved with it.
    const [summaryResult, page] = await Promise.all([
      fetchRatingSummary(props.venuePublicId),
      fetchReviews(props.venuePublicId, { limit: PAGE_SIZE }),
    ])
    summary.value = summaryResult
    rows.value = page.rows
    total.value = page.total
    comment.value = saved.comment ?? ''
  } catch (err) {
    // 403 means the visit has not happened yet, or the contact is not theirs.
    // Saying so plainly is more use than "could not save".
    sendError.value =
      errorStatus(err) === 403
        ? 'Only someone who has played here can rate it.'
        : errorStatus(err) === 400
          ? 'Enter the contact you booked with.'
          : errorDetail(err, 'Could not save your rating.')
  } finally {
    sending.value = false
  }
}

load()
</script>

<template>
  <section class="reviews space-y-5">
    <header class="space-y-1">
      <h2 class="text-xl font-bold tracking-tight text-gray-900">
        What visitors said<span v-if="venueName"> about {{ venueName }}</span>
      </h2>
      <p v-if="loading && !summary" class="breathe text-sm text-gray-500">Loading reviews…</p>
      <p v-else-if="loadError" class="text-sm text-red-600" role="alert">{{ loadError }}</p>
      <p v-else-if="!summary?.count" class="text-sm text-gray-600">
        No ratings yet. Played here? Leave the first one.
      </p>
      <div v-else class="flex items-center gap-3">
        <p class="text-3xl font-bold text-gray-900">{{ summary.average }}</p>
        <div class="space-y-0.5">
          <p class="text-amber-500" :aria-label="`${summary.average} out of 5`">
            <span v-for="n in 5" :key="n" :class="n <= starsOf(summary.average) ? 'text-amber-500' : 'text-gray-300'">
              ★
            </span>
          </p>
          <p class="text-xs text-gray-500">{{ summary.count }} {{ summary.count === 1 ? 'rating' : 'ratings' }}</p>
        </div>
      </div>
    </header>

    <div v-if="summary?.count" class="reviews-bars space-y-1">
      <div v-for="star in 5" :key="star" class="reviews-bar-row">
        <span class="reviews-bar-label">{{ star }} ★</span>
        <span class="reviews-bar-track">
          <span
            class="reviews-bar-fill"
            :style="{ width: distributionBar(summary.distribution?.[star]) }"
          />
        </span>
        <span class="reviews-bar-count">{{ summary.distribution?.[star] ?? 0 }}</span>
      </div>
    </div>

    <form class="reviews-form space-y-3 rounded-2xl border border-gray-300 bg-white p-4" @submit.prevent="submit">
      <h3 class="text-sm font-semibold text-gray-900">
        {{ mine ? 'Change your rating' : 'Rate this place' }}
      </h3>

      <div class="flex items-center gap-1" role="radiogroup" aria-label="Your rating">
        <button
          v-for="n in 5"
          :key="n"
          type="button"
          role="radio"
          :aria-checked="stars === n"
          :aria-label="`${n} star${n === 1 ? '' : 's'}`"
          class="reviews-star tappable text-2xl"
          :class="n <= stars ? 'text-amber-500' : 'text-gray-300'"
          @click="stars = n"
        >
          ★
        </button>
        <span class="ml-2 text-xs text-gray-500">
          {{ stars ? `${stars} of 5` : 'Pick a rating' }}
        </span>
      </div>

      <label class="block space-y-1">
        <span class="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Comment <span class="normal-case font-normal">(optional)</span>
        </span>
        <textarea
          v-model="comment"
          rows="2"
          maxlength="2000"
          placeholder="Cold floor, good light, easy to park…"
          class="reviews-input w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
      </label>

      <label v-if="!customer.isSignedIn" class="block space-y-1">
        <span class="text-xs font-semibold uppercase tracking-wide text-gray-500">
          The contact you booked with
        </span>
        <input
          v-model="contact"
          type="text"
          name="customer_contact"
          placeholder="0812… or you@example.com"
          class="reviews-input w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <span class="block text-xs text-gray-500">
          Signed in?
          <RouterLink :to="{ name: 'login', query: { as: 'customer' } }" class="font-semibold text-gray-900 underline">
            Sign in
          </RouterLink>
          and it fills itself in.
        </span>
      </label>

      <button
        type="submit"
        class="reviews-submit rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        :disabled="sending || !stars"
      >
        {{ sending ? 'Saving…' : mine ? 'Update rating' : 'Post rating' }}
      </button>

      <p v-if="notice" class="text-sm text-emerald-700" role="status">{{ notice }}</p>
      <p v-if="sendError" class="text-sm text-red-600" role="alert">{{ sendError }}</p>
    </form>

    <ul v-if="rows.length" class="space-y-3">
      <li
        v-for="(row, index) in rows"
        :key="row.public_id"
        class="stagger-item reviews-item rounded-2xl border border-gray-200 bg-white p-4"
        :style="{ animationDelay: `${Math.min(index, 8) * 40}ms` }"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-gray-900">
              {{ row.author }}
              <span v-if="row.mine" class="ml-1 text-xs font-normal text-gray-500">(you)</span>
            </p>
            <p class="text-amber-500" :aria-label="`${row.rating} out of 5`">
              <span v-for="n in 5" :key="n" :class="n <= row.rating ? 'text-amber-500' : 'text-gray-300'">
                ★
              </span>
            </p>
          </div>
          <p class="shrink-0 text-xs text-gray-500">{{ formatLongDate(row.created_at?.slice(0, 10)) }}</p>
        </div>
        <p v-if="row.comment" class="mt-2 text-sm text-gray-700">{{ row.comment }}</p>
      </li>
    </ul>

    <p v-else-if="!loading && !loadError" class="text-sm text-gray-500">Nothing written yet.</p>

    <button
      v-if="hasMore"
      type="button"
      class="reviews-more rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50"
      :disabled="loading"
      @click="loadMore"
    >
      {{ loading ? 'Loading…' : `Show more (${rows.length} of ${total})` }}
    </button>
  </section>
</template>