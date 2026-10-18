import { createPinia } from 'pinia'
import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router/index.js'
import { useCustomerStore } from './stores/customer.js'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// Confirm a stored customer token still works before the first screen that
// depends on it. Not awaited on purpose: the app renders immediately and the
// answer arrives when it arrives — a signed-out customer sees the same pages,
// just without their history attached.
useCustomerStore().restore()

app.mount('#app')
