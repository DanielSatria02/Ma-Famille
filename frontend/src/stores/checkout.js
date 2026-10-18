import { defineStore } from 'pinia'
import { ref } from 'vue'

// Holds the order handed over to the payment gateway, plus the gateway session
// opened for it.
// order: { bookingId, groupId, facilityKey, facility, date, startHour, endHour,
//          hours, hourlyRate, total }
// gateway: { status: 'ready'|'unconfigured'|'failed', invoice_number, checkout_url }
export const useCheckoutStore = defineStore('checkout', () => {
  const pendingOrder = ref(null)
  const gateway = ref(null)

  function setOrder(order) {
    pendingOrder.value = order
    gateway.value = null
  }

  function setGateway(state) {
    gateway.value = state
  }

  function clearOrder() {
    pendingOrder.value = null
    gateway.value = null
  }

  return { pendingOrder, gateway, setOrder, setGateway, clearOrder }
})
