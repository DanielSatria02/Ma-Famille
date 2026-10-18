<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import loginBackground from '../assets/loginbg.avif'
import { useCustomerStore } from '../stores/customer.js'
import '../styles/login.css'

// One screen for both: most people arrive to sign in, and switching to
// registering should not lose what they already typed.
const router = useRouter()
const customer = useCustomerStore()

const mode = ref('signin')
const email = ref('')
const password = ref('')
const displayName = ref('')
const phone = ref('')

const isRegistering = computed(() => mode.value === 'register')
const title = computed(() => (isRegistering.value ? 'Create your account' : 'Welcome back'))
const submitLabel = computed(() =>
  isRegistering.value ? 'Create account' : 'Sign in',
)

function switchMode() {
  mode.value = isRegistering.value ? 'signin' : 'register'
  // The error belonged to the other form.
  customer.error = ''
}

async function handleSubmit() {
  const payload = { email: email.value.trim(), password: password.value }
  const ok = isRegistering.value
    ? await customer.register({ ...payload, displayName: displayName.value, phone: phone.value.trim() })
    : await customer.login(payload)
  if (ok) {
    password.value = ''
    await router.push({ name: 'my-bookings' })
    return
  }
  password.value = ''
}
</script>

<template>
  <section
    class="login-page relative isolate -mx-4 -my-6 flex min-h-[calc(100vh-10rem)] max-w-none items-center justify-center overflow-hidden px-4 py-10"
  >
    <div
      class="absolute inset-0 -z-20 bg-cover bg-center bg-no-repeat"
      :style="{ backgroundImage: `url(${loginBackground})` }"
      aria-hidden="true"
    />
    <div class="login-overlay absolute inset-0 -z-10" aria-hidden="true" />

    <div class="w-full max-w-md space-y-8">
      <div class="space-y-3 text-center">
        <p class="login-eyebrow text-sm font-semibold uppercase tracking-[0.2em]">
          Ma Famille
        </p>
        <h1 class="login-title text-3xl tracking-tight">{{ title }}</h1>
        <p class="login-description">
          An account keeps your bookings together — no more retyping your number
          to find them.
        </p>
      </div>

      <form class="login-card space-y-5 rounded-2xl border p-6 shadow-sm" @submit.prevent="handleSubmit">
        <div v-if="isRegistering" class="space-y-2">
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
            :autocomplete="isRegistering ? 'new-password' : 'current-password'"
            :placeholder="isRegistering ? 'At least 8 characters' : 'Enter your password'"
            :minlength="isRegistering ? 8 : undefined"
            required
            class="login-input w-full rounded-lg border px-3 py-2.5 outline-none transition"
          />
        </div>

        <div v-if="isRegistering" class="space-y-2">
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

        <button
          type="submit"
          class="login-button w-full rounded-lg px-4 py-2.5 font-semibold transition disabled:opacity-50"
          :disabled="customer.loading"
        >
          {{ customer.loading ? 'One moment…' : submitLabel }}
        </button>

        <p v-if="customer.error" class="login-body-text text-center text-sm" role="alert">
          {{ customer.error }}
        </p>

        <p class="login-body-text text-center text-sm">
          {{ isRegistering ? 'Already have an account?' : 'No account yet?' }}
          <button type="button" class="login-link font-medium" @click="switchMode">
            {{ isRegistering ? 'Sign in' : 'Create one' }}
          </button>
        </p>
      </form>
    </div>
  </section>
</template>
