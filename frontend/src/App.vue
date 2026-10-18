<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppNav from './components/AppNav.vue'
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
        Keyed on the path so each view is its own transition. Without the key
        Vue reuses one element between routes and the animation would only
        ever play on the first page.

        The duration is given explicitly. Left to itself Vue ends the
        transition on the browser's `transitionend`, and if that event never
        arrives — a throttled background tab, a busy main thread — the classes
        stay on the element, which leaves it at zero opacity. That is a blank
        page with no way back. A duration makes Vue finish on a timer it owns.
      -->
      <RouterView v-slot="{ Component, route: view }">
        <Transition name="fade" mode="out-in" :duration="250">
          <component :is="Component" :key="view.path" />
        </Transition>
      </RouterView>
    </main>
    <footer v-if="!bare" class="border-t border-gray-200 py-4 text-center text-sm text-gray-500">
      ma-famille · Sports Venue Booking
    </footer>
  </div>
</template>