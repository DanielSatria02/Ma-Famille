import { createRouter, createWebHistory } from 'vue-router'

import { PREMIERE_FRANCHISE } from '../config/franchise.js'
import { useAuthStore } from '../stores/auth.js'
import { useCustomerStore } from '../stores/customer.js'
import HomeView from '../views/HomeView.vue'
import BookingView from '../views/BookingView.vue'
import HealthView from '../views/HealthView.vue'
import LoginView from '../views/LoginView.vue'
import ManagerHomeView from '../views/ManagerHomeView.vue'
import MyBookingsView from '../views/MyBookingsView.vue'
import PaymentView from '../views/PaymentView.vue'

// Everything past the door needs an account: a booking belongs to somebody, and
// a visitor who only has to type a phone number into a lookup box can read
// another person's visit history by guessing a number that happens to be a
// customer here. Two routes stay open on purpose — the front page is what tells
// a visitor what this is before we ask them for anything, and /health is how
// anyone finds out whether the thing is working at all.
const PUBLIC_ROUTES = new Set(['home', 'health', 'login'])

// meta.franchise sets the brand name shown in the header.
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/health', name: 'health', component: HealthView },
    { path: '/my-bookings', name: 'my-bookings', component: MyBookingsView },
    // One door for both accounts. `?as=manager` opens the manager tab; without
    // it the customer tab is showing, which is what most visitors want.
    { path: '/login', name: 'login', component: LoginView },
    { path: '/account', redirect: (to) => ({ name: 'login', query: to.query }) },
    {
      path: '/manager',
      name: 'manager-home',
      component: ManagerHomeView,
      meta: { franchise: PREMIERE_FRANCHISE, requires: 'manager' },
    },
    {
      path: '/booking',
      name: 'booking',
      component: BookingView,
      meta: { franchise: PREMIERE_FRANCHISE, gradient: true },
    },
    {
      path: '/payment',
      name: 'payment',
      component: PaymentView,
      meta: { franchise: PREMIERE_FRANCHISE, gradient: true },
    },
  ],
})

// One guard for the whole app rather than a beforeEnter per route: a new route
// added later is protected by default, not by someone remembering to add a
// line to it.
router.beforeEach(async (to) => {
  if (PUBLIC_ROUTES.has(to.name)) return true

  if (to.meta.requires === 'manager') {
    // The dashboard writes with the manager token, so ask for that login first.
    return useAuthStore().isLoggedIn ? true : { name: 'login', query: { as: 'manager' } }
  }

  const customer = useCustomerStore()
  // A token in storage is not yet a session: it may have been revoked, or it
  // may have expired overnight. Confirming it here means a guard that passed on
  // a stale token cannot walk into a page that will then show "not signed in".
  if (customer.token && !customer.isSignedIn) await customer.restore()
  if (customer.isSignedIn) return true

  // `from` is kept so signing in returns the visitor to where they were going,
  // instead of dropping them on the home page after trying to book.
  return { name: 'login', query: to.name === 'login' ? to.query : { next: to.fullPath } }
})

export default router