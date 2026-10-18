<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DEFAULT_FRANCHISE } from '../config/franchise.js'
import { useAppStore } from '../stores/app.js'
import { useAuthStore } from '../stores/auth.js'
import { useCustomerStore } from '../stores/customer.js'
import '../styles/header.css'

const store = useAppStore()
const auth = useAuthStore()
const customer = useCustomerStore()
const route = useRoute()
const router = useRouter()
const isSidebarOpen = ref(false)

const isManagerArea = computed(() => route.path.startsWith('/manager'))
const homePath = computed(() => (isManagerArea.value ? '/manager' : '/'))
const brandName = computed(() => route.meta.franchise ?? DEFAULT_FRANCHISE)

const dotClass = computed(() => {
  if (store.backendStatus === 'ok') return 'bg-green-600'
  if (store.backendStatus === 'unknown') return 'bg-gray-400'
  return 'bg-red-600'
})

onMounted(() => {
  store.checkBackend()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})

function toggleSidebar() {
  isSidebarOpen.value = !isSidebarOpen.value
}

function closeSidebar() {
  isSidebarOpen.value = false
}

function handleKeydown(event) {
  if (event.key === 'Escape') closeSidebar()
}

// Log out: drop the manager token and go back to the login page.
function logOut() {
  auth.logout()
  closeSidebar()
  router.push({ name: 'login' })
}

// Sign out of a customer account. The visit ends either way — a failed call
// must not leave someone stuck signed in on a shared device.
async function signOut() {
  await customer.logout()
  closeSidebar()
  router.push({ name: 'account' })
}
</script>

<template>
  <header class="app-header">
    <div class="app-header-bar flex items-center justify-between border-b px-4 py-3">
      <RouterLink :to="homePath" class="app-header-brand font-bold no-underline">{{ brandName }}</RouterLink>
      <div class="flex items-center gap-4">
        <span :class="['h-2.5 w-2.5 rounded-full', dotClass]" :title="`backend: ${store.backendStatus}`" />
        <button
          type="button"
          class="app-header-menu-button rounded-lg p-2 transition focus:outline-none focus:ring-2 focus:ring-gray-400"
          aria-label="Open menu"
          :aria-expanded="isSidebarOpen"
          aria-controls="app-sidebar"
          @click="toggleSidebar"
        >
          <span class="flex flex-col items-center gap-1" aria-hidden="true">
            <span class="h-1 w-1 rounded-full bg-current" />
            <span class="h-1 w-1 rounded-full bg-current" />
            <span class="h-1 w-1 rounded-full bg-current" />
          </span>
        </button>
      </div>
    </div>

    <div
      v-if="isSidebarOpen"
      class="app-header-backdrop fixed inset-0 z-40"
      aria-hidden="true"
      @click="closeSidebar"
    />

    <aside
      id="app-sidebar"
      class="app-sidebar fixed right-0 top-0 z-50 flex h-full w-72 max-w-[85vw] flex-col border-l p-6 shadow-xl"
      :class="{ 'is-open': isSidebarOpen }"
      :aria-hidden="!isSidebarOpen"
      :inert="!isSidebarOpen"
    >
      <div class="mb-8 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-900">Menu</h2>
        <button
          type="button"
          class="rounded-lg p-2 text-gray-600 transition hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-400"
          aria-label="Close menu"
          @click="closeSidebar"
        >
          <span class="text-2xl leading-none" aria-hidden="true">&times;</span>
        </button>
      </div>

      <nav class="flex flex-col gap-2">
        <RouterLink :to="homePath" class="app-sidebar-link rounded-lg px-3 py-2 no-underline" @click="closeSidebar">Home</RouterLink>
        <RouterLink to="/health" class="app-sidebar-link rounded-lg px-3 py-2 no-underline" @click="closeSidebar">Health</RouterLink>
        <RouterLink v-if="!isManagerArea" to="/my-bookings" class="app-sidebar-link rounded-lg px-3 py-2 no-underline" @click="closeSidebar">My bookings</RouterLink>
        <RouterLink v-if="!isManagerArea" to="/login" class="app-sidebar-link rounded-lg px-3 py-2 no-underline" @click="closeSidebar">Manager login</RouterLink>
        <RouterLink v-if="isManagerArea" :to="homePath" class="app-sidebar-link rounded-lg px-3 py-2 no-underline" @click="closeSidebar">Dashboard</RouterLink>
        <button type="button" class="app-sidebar-link rounded-lg px-3 py-2 text-left" @click="logOut">Log out</button>

        <!-- A customer's account. The name is shown when signed in so it is
             obvious whose bookings "My bookings" will list. -->
        <RouterLink
          v-if="!isManagerArea"
          to="/account"
          class="app-sidebar-link rounded-lg px-3 py-2 no-underline"
          @click="closeSidebar"
        >
          {{ customer.isSignedIn ? customer.displayName || 'Account' : 'Sign in' }}
        </RouterLink>
        <button
          v-if="!isManagerArea && customer.isSignedIn"
          type="button"
          class="app-sidebar-link rounded-lg px-3 py-2 text-left"
          @click="signOut"
        >
          Sign out
        </button>
      </nav>
    </aside>
  </header>
</template>
