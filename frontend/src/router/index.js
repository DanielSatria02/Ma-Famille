import { createRouter, createWebHistory } from 'vue-router'

import { PREMIERE_FRANCHISE } from '../config/franchise.js'
import { useAuthStore } from '../stores/auth.js'
import BookingView from '../views/BookingView.vue'
import HealthView from '../views/HealthView.vue'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import ManagerHomeView from '../views/ManagerHomeView.vue'
import PaymentView from '../views/PaymentView.vue'

// meta.franchise sets the brand name shown in the header.
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/health', name: 'health', component: HealthView },
    { path: '/login', name: 'login', component: LoginView },
    {
      path: '/manager',
      name: 'manager-home',
      component: ManagerHomeView,
      meta: { franchise: PREMIERE_FRANCHISE },
      // The dashboard writes with the manager token, so ask for the login first.
      beforeEnter: () => (useAuthStore().isLoggedIn ? true : { name: 'login' }),
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

export default router
