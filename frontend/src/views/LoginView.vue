<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import loginBackground from '../assets/loginbg.avif'
import { useAuthStore } from '../stores/auth.js'
import { useCustomerStore } from '../stores/customer.js'
import '../styles/login.css'

// One door, two kinds of people.
//
// Two separate pages used to ask for an email and a password in almost the
// same words, and the navigation offered both — so arriving to book felt like
// finding the wrong link. A tab says plainly which account is wanted and keeps
// the fields, the styling and the error in one place.
//
// A manager is a venue owner signing in to run a dashboard; a customer is
// someone keeping their own bookings together. They are different accounts
// with different doors, and nothing here pretends otherwise: signing in as one
// does not sign you in as the other.

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const customer = useCustomerStore()

const TABS = [
  { id: 'customer', label: 'Customer' },
  { id: 'manager', label: 'Venue manager' },
]

// The old deep links still land on the right tab: /account is the customer
// door, /login?as=manager is the dashboard door.
const tab = ref(route.query.as === 'manager' ? 'manager' : 'customer')
const isManager = computed(() => tab.value === 'manager')

const email = ref('')
const password = ref('')
const displayName = ref('')
const phone = ref('')
const rememberMe = ref(false)

const registering = ref(false)
// Registration is a customer's business; a manager does not register here.
const showRegister = computed(() => !isManager.value && registering.value)

// Where to go once through the door. The guard sends people here with `next`
// when they were on their way somewhere, so a visitor who tried to book and
// had to sign in first lands on the booking form, not on the home page.
const destination = computed(() => {
  const next = route.query.next
  // Only same-site paths: an attacker-supplied `//evil.test` must not become
  // the place we send someone straight after they hand over a password.
  if (typeof next === 'string' && next.startsWith('/') && !next.startsWith('//')) return next
  return isManager.value ? '/manager' : '/my-bookings'
})

// One error slot for whichever account is being tried: only one form is
// visible, so two errors would be noise.
const error = computed(() => (isManager.value ? auth.error : customer.error))
const busy = computed(() => (isManager.value ? auth.loading : customer.loading))

function selectTab(next) {
  if (tab.value === next) return
  tab.value = next
  // An address meant for one door is not a valid guess at the other, and an
  // error left over from the other form would read as this one's failure.
  password.value = ''
  auth.error = ''
  customer.error = ''
  registering.value = false
}

function switchMode() {
  registering.value = !registering.value
  customer.error = ''
}

async function handleSubmit() {
  const payload = { email: email.value.trim(), password: password.value }
  let ok
  if (isManager.value) {
    ok = await auth.login(payload)
    if (ok) {
      await router.push({ name: 'manager-home' })
      return
    }
  } else {
    ok = registering.value
      ? await customer.register({
          ...payload,
          displayName: displayName.value,
          phone: phone.value.trim(),
        })
      : await customer.login(payload)
    if (ok) {
      await router.push(destination.value)
      return
    }
  }
  // A failed attempt never leaves the password sitting in the field.
  password.value = ''
}

const headline = computed(() => {
  if (isManager.value) return 'Ma Famille!'
  return registering.value ? 'Create your account' : 'Welcome back'
})

const description = computed(() => {
  if (isManager.value) return 'Sign in to run your venue dashboard'
  if (registering.value) return 'One account keeps every booking and cancellation together'
  // Say why the door is here, or it reads as an arbitrary hurdle.
  return 'Your bookings, cancellations and receipts live behind this'
})

const submitLabel = computed(() => {
  if (isManager.value) return 'Sign in'
  return registering.value ? 'Create account' : 'Sign in'
})
</script>

<template>
  <!--
    No negative margins here. This page is the one view that opts out of the
    header and footer, so <main> gives it no padding at all and it is already the
    full width of the screen. The -mx-4 that used to be here was left over from
    when the page sat inside the padded main: it pushed the section 16px past the
    left edge, and a box 16px wider than the viewport gives the document a
    horizontal scrollbar on every screen size.
  -->
  <section class="login-page relative isolate flex min-h-dvh w-full max-w-none items-center justify-center overflow-hidden px-4 py-10">
    <div
      class="absolute inset-0 -z-20 bg-cover bg-center bg-no-repeat"
      :style="{ backgroundImage: `url(${loginBackground})` }"
      aria-hidden="true"
    />
    <div class="login-overlay absolute inset-0 -z-10" aria-hidden="true" />

    <div class="w-full max-w-md space-y-6">
      <!--
        Tabs rather than two pages: the choice is "which account", which is one
        decision, so it should look like one place with a switch in it.
      -->
      <div class="login-tabs grid grid-cols-2 gap-1 rounded-xl border p-1" role="tablist" aria-label="Account type">
        <button
          v-for="option in TABS"
          :key="option.id"
          type="button"
          role="tab"
          :aria-selected="tab === option.id"
          class="login-tab rounded-lg px-3 py-2 text-sm font-semibold transition"
          :class="{ 'login-tab-active': tab === option.id }"
          @click="selectTab(option.id)"
        >
          {{ option.label }}
        </button>
      </div>

      <div class="space-y-2 text-center">
        <p class="login-eyebrow text-sm font-semibold uppercase tracking-[0.2em]">Ma Famille</p>
        <h1 class="login-title text-3xl tracking-tight">{{ headline }}</h1>
        <p class="login-description">{{ description }}</p>
      </div>

      <form class="login-card space-y-5 rounded-2xl border p-6 shadow-sm" @submit.prevent="handleSubmit">
        <div v-if="showRegister" class="space-y-2">
          <label for="name" class="login-label block text-sm font-medium">Name on bookings</label>
          <input
            id="name"
            v-model="displayName"
            type="text"
            name="name"
            autocomplete="name"
            required
            placeholder="Your name"
            class="login-input w-full rounded-lg border px-3 py-2.5 outline-none transition"
          />
        </div>

        <div class="space-y-2">
          <label for="email" class="login-label block text-sm font-medium">Email address</label>
          <input
            id="email"
            v-model="email"
            type="email"
            name="email"
            autocomplete="email"
            required
            placeholder="you@example.com"
            class="login-input w-full rounded-lg border px-3 py-2.5 outline-none transition"
          />
        </div>

        <div class="space-y-2">
          <label for="password" class="login-label block text-sm font-medium">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            name="password"
            :autocomplete="showRegister ? 'new-password' : 'current-password'"
            :placeholder="showRegister ? 'At least 8 characters' : 'Enter your password'"
            :minlength="showRegister ? 8 : undefined"
            required
            class="login-input w-full rounded-lg border px-3 py-2.5 outline-none transition"
          />
        </div>

        <div v-if="showRegister" class="space-y-2">
          <label for="phone" class="login-label block text-sm font-medium">
            WhatsApp number <span class="login-body-text-acc">(optional)</span>
          </label>
          <input
            id="phone"
            v-model="phone"
            type="tel"
            name="phone"
            autocomplete="tel"
            placeholder="0812…"
            class="login-input w-full rounded-lg border px-3 py-2.5 outline-none transition"
          />
          <p class="login-body-text text-xs">
            The venue reaches you here. Leave it blank and we use your email.
          </p>
        </div>

        <!--
          Only where it means something: the manager's session already survives
          a restart, and a checkbox that does nothing is worse than none.
        -->
        <div v-if="isManager" class="flex items-center justify-between gap-4 text-sm">
          <label class="login-body-text flex items-center gap-2">
            <input
              v-model="rememberMe"
              type="checkbox"
              class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            Remember me
          </label>
        </div>

        <button
          type="submit"
          class="login-button w-full rounded-lg px-4 py-2.5 font-semibold transition disabled:opacity-50"
          :disabled="busy"
        >
          {{ busy ? 'One moment…' : submitLabel }}
        </button>

        <p v-if="error" class="login-body-text text-center text-sm" role="alert">{{ error }}</p>

        <p v-if="!isManager" class="login-body-text text-center text-sm">
          {{ registering ? 'Already have an account?' : 'No account yet?' }}
          <button type="button" class="login-link font-medium" @click="switchMode">
            {{ registering ? 'Sign in' : 'Create one' }}
          </button>
        </p>
      </form>
    </div>
  </section>
</template>