import { useCheckoutStore } from '../stores/checkout.js'

// Payment gateway boundary. No gateway is connected yet: this only records the order
// so the payment page can show it. Replace the body with the real gateway call
// (e.g. create a checkout session and redirect to its URL) when it is available.
export async function startCheckout(order) {
  useCheckoutStore().setOrder(order)
  return { redirect: { name: 'payment' } }
}
