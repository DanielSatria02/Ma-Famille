<script setup>
import StatCard from './StatCard.vue'

defineProps({
  weeklyVisitors: { type: Number, default: 0 },
  todaysBookings: { type: Number, default: 0 },
  canceledBookings: { type: Number, default: 0 },
})
</script>

<template>
  <section class="stats" aria-label="Booking overview">
    <StatCard :value="weeklyVisitors" label="This Week's Visitor">
      <template #icon>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M3 10h18M8 3v4M16 3v4" />
        </svg>
      </template>
    </StatCard>

    <StatCard :value="todaysBookings" label="Today's Booking">
      <template #icon>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="9.5" cy="9.5" rx="6.5" ry="7" transform="rotate(-45 9.5 9.5)" />
          <path d="M14.5 14.5 20 20M6 9.5h7M9.5 6v7" />
        </svg>
      </template>
    </StatCard>

    <StatCard :value="canceledBookings" label="Canceled booking">
      <template #icon>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
      </template>
    </StatCard>
  </section>
</template>
