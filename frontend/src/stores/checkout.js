import { defineStore } from 'pinia'
import { ref } from 'vue'

// Holds the order handed over to the payment gateway.
// order: { facilityKey, facility, date, startHour, endHour, hours, hourlyRate, total }
export const useCheckoutStore = defineStore('checkout', () => {
  const pendingOrder = ref(null)

  function setOrder(order) {
    pendingOrder.value = order
  }

  function clearOrder() {
    pendingOrder.value = null
  }

  return { pendingOrder, setOrder, clearOrder }
})
