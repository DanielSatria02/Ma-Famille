import { createPayment, errorStatus } from './api.js'
import { useCheckoutStore } from '../stores/checkout.js'

// Payment gateway boundary. The booking already exists when this runs; this
// opens the DOKU checkout session for it. A 501 means the server has no DOKU
// keys yet (local dev), so the page says so instead of pretending to pay.
export async function startCheckout(order) {
  const store = useCheckoutStore()
  store.setOrder(order)

  if (!order.bookingId) {
    store.setGateway({ status: 'failed' })
    return { redirect: { name: 'payment' } }
  }

  try {
    const payment = await createPayment(order.bookingId, { amount: order.total, kind: 'full' })
    store.setGateway({ status: 'ready', ...payment })
  } catch (err) {
    store.setGateway({ status: errorStatus(err) === 501 ? 'unconfigured' : 'failed' })
  }

  return { redirect: { name: 'payment' } }
}
