<script setup>
import { RouterLink } from 'vue-router'

// A URL that matches nothing. Without this, Vue Router leaves to.name undefined,
// the guard treats it as a route needing an account, and a mistyped address sends
// the visitor to the login page as though they had asked for something private.
</script>

<template>
  <section class="mx-auto max-w-md py-12 text-center">
    <p class="text-sm font-semibold uppercase tracking-wide text-gray-500">404</p>
    <h1 class="mt-2 text-3xl font-bold tracking-tight text-gray-900">This page does not exist</h1>
    <p class="mt-3 text-sm text-gray-600">
      The address may have a typo in it, or the page may have moved.
    </p>
    <RouterLink
      :to="{ name: 'home' }"
      class="mt-6 inline-flex min-h-11 items-center rounded-lg bg-gray-900 px-5 text-sm font-semibold text-white"
    >
      Back to the front page
    </RouterLink>
  </section>
</template>