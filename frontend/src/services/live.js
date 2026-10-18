import { API_ORIGIN } from './api.js'

// One live connection to the backend's booking stream.
//
// The payment page used to ask every five seconds whether its booking had
// settled. The server already knows the moment that changes, so it says so.
// Polling had one real advantage and it was a bug: it could not know that a
// client had gone away, so a closed tab kept the interval running until the
// page finally unloaded.

const RECONNECT_BASE_MS = 500
const RECONNECT_MAX_MS = 10000

// `API_ORIGIN` is http(s); a websocket needs ws(s) on the same host and port.
function socketUrl(publicId) {
  const url = new URL(API_ORIGIN)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  // The API version prefix is the one the socket route is mounted under.
  const prefix = url.pathname.endsWith('/v1') ? url.pathname : `${url.pathname.replace(/\/$/, '')}/v1`
  url.pathname = `${prefix}/ws/bookings/${publicId}`
  url.search = ''
  return url.toString()
}

/**
 * Watch one booking. Calls `onUpdate` with the server's current state on
 * connect and again on every change; calls `onStatus` with the connection's
 * own state so the page can say so rather than silently looking stuck.
 *
 * Reconnects with a backoff, because a dropped connection is normal (sleeping
 * laptop, tunnel) and a client that never came back would leave the customer
 * staring at a booking that quietly changed without them.
 */
export function watchBooking(publicId, { onUpdate, onStatus } = {}) {
  let socket = null
  let retryTimer = null
  let attempt = 0
  let closedByUs = false

  function scheduleReconnect() {
    if (closedByUs || !publicId) return
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS)
    attempt += 1
    retryTimer = setTimeout(open, delay)
  }

  function open() {
    if (closedByUs || !publicId) return
    onStatus?.('connecting')
    try {
      socket = new WebSocket(socketUrl(publicId))
    } catch {
      scheduleReconnect()
      return
    }

    socket.onopen = () => {
      attempt = 0
      onStatus?.('live')
    }

    socket.onmessage = (event) => {
      let payload
      try {
        payload = JSON.parse(event.data)
      } catch {
        // A frame we cannot read is not worth tearing the connection down for.
        return
      }
      onUpdate?.(payload)
    }

    socket.onerror = () => {
      // `onclose` always follows, and it owns the retry.
    }

    socket.onclose = () => {
      socket = null
      if (closedByUs) return
      onStatus?.('offline')
      scheduleReconnect()
    }
  }

  open()

  return function stop() {
    closedByUs = true
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    if (socket) {
      socket.onclose = null
      socket.close()
      socket = null
    }
  }
}