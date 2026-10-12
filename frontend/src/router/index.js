import { createRouter, createWebHistory } from 'vue-router'

import HealthView from '../views/HealthView.vue'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import ManagerHomeView from '../views/ManagerHomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/health', name: 'health', component: HealthView },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/manager', name: 'manager-home', component: ManagerHomeView },
  ],
})

export default router
