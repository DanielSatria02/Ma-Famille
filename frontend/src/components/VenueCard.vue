<script setup>
import '../styles/venue-card.css'
import { initialOf } from '../utils/image.js'
import { formatRupiah } from '../utils/money.js'

defineProps({
  image: { type: String, default: '' },
  title: { type: String, default: '' },
  location: { type: String, default: '' },
  openTime: { type: String, default: '' },
  closeTime: { type: String, default: '' },
  tags: { type: Array, default: () => [] },
  courts: { type: Number, default: 0 },
  fromPrice: { type: Number, default: 0 },
  isChosen: { type: Boolean, default: false },
})

defineEmits(['select'])
</script>

<template>
  <!--
    The whole card is the control, because picking a club is the only thing
    this card does. It used to carry a "Check availability" button that fetched
    a date list and left it sitting there, so the visitor had chosen nothing
    and still had a page of grey days to look at.

    The brand is on the card and not only in the header because this is a
    franchise: a player choosing between two clubs is choosing between two
    branches, and the branch is what the card is about.
  -->
  <button
    type="button"
    class="venue-card tappable"
    :class="{ 'is-chosen': isChosen }"
    :aria-pressed="isChosen"
    @click="$emit('select')"
  >
    <span class="venue-card-image">
      <img v-if="image" :src="image" alt="" class="venue-card-image-el" />
      <span v-else class="venue-card-image-empty" aria-hidden="true">{{ initialOf(title) }}</span>
    </span>

    <span class="venue-card-body">
      <span class="venue-card-brand">Ma-Famille Premiere</span>
      <span class="venue-card-title">{{ title }}</span>
      <span class="venue-card-location">{{ location }}</span>

      <span class="venue-card-hours">
        <svg
          class="venue-card-clock-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span class="venue-card-hours-text">{{ openTime }} - {{ closeTime }}</span>
      </span>

      <span class="venue-card-facts">
        <span v-if="courts" class="venue-card-fact">
          {{ courts }} {{ courts === 1 ? 'court' : 'courts' }}
        </span>
        <span v-if="fromPrice" class="venue-card-fact">from {{ formatRupiah(fromPrice) }}/hour</span>
      </span>

      <span class="venue-card-tags">
        <span v-for="tag in tags" :key="tag" class="venue-card-tag">{{ tag }}</span>
      </span>

      <span class="venue-card-action">
        <span class="venue-card-button">
          {{ isChosen ? 'Selected' : 'See days' }}
        </span>
      </span>
    </span>
  </button>
</template>
