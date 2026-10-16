import { addDays, toIsoDate } from './date.js'

// Bookings must be made at least one day ahead (H-1): today and past dates are not bookable.
export function minBookableDate(now = new Date()) {
  return toIsoDate(addDays(now, 1))
}

export function isBookableDate(isoDate, now = new Date()) {
  return Boolean(isoDate) && isoDate >= minBookableDate(now)
}

const hourOf = (time) => Number.parseInt(time, 10)

// Hours (0-23) already booked by other clients for a venue on a date.
export function takenHours(bookings, venueName, isoDate) {
  const hours = new Set()
  for (const booking of bookings) {
    if (booking.venueName !== venueName || booking.date !== isoDate) continue
    for (let hour = hourOf(booking.startTime); hour < hourOf(booking.endTime); hour += 1) hours.add(hour)
  }
  return hours
}

// True when any hour in [startHour, endHour) is already taken.
export function hasConflict(taken, startHour, endHour) {
  for (let hour = startHour; hour < endHour; hour += 1) {
    if (taken.has(hour)) return true
  }
  return false
}
