<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppNav from './components/AppNav.vue'
import { BRAND_NAME } from './config/brand.js'
import './styles/page.css'

const route = useRoute()
// The login screen is full-bleed on purpose — it has its own background and
// takes the whole window — so the chrome around it would only crowd it. The
// footer goes with it: "foundation iteration" is a note to ourselves, not
// something to greet a customer with.
const bare = computed(() => route.name === 'login')
</script>

<template>
  <div :class="['flex min-h-screen flex-col text-gray-900', route.meta.gradient ? 'page-gradient' : 'bg-white']">
    <AppNav v-if="!bare" />
    <main :class="['mx-auto w-full flex-1', bare ? 'max-w-none' : 'max-w-4xl px-4 py-6']">
      <!--
        Keyed on the path, so each view gets a fresh element and its own entrance
        instead of being patched into whatever was on screen before. Without the
        key Vue would reuse one element and the animation would only ever play
        on the first page.

        There is deliberately no `<Transition>` around this. `out-in` waits for
        the leaving view to finish before mounting the arriving one, so anything
        that stops the leave transition from completing leaves the old page on
        screen while the URL has already changed — the address bar reads
        /booking and the login form is still sitting there. A transition with no
        ordering to it cannot get stuck.
      -->
      <RouterView v-slot="{ Component, route: view }">
        <div class="view-enter-active">
          <component :is="Component" :key="view.path" />
        </div>
      </RouterView>
    </main>
    <footer v-if="!bare" class="border-t border-gray-200 py-4 text-center text-sm text-gray-500">
      {{ BRAND_NAME }} · Padel Court Booking
    </footer>
  </div>
</template>