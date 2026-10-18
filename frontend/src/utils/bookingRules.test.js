import { describe, expect, it } from 'vitest'

import { hasConflict, isBookableDate, minBookableDate, takenHours } from './bookingRules.js'

describe('the H-1 rule', () => {
  // A booking must be made a day ahead: today is not bookable.
  it('makes tomorrow the earliest bookable date', () => {
    expect(minBookableDate(new Date(2026, 9, 19, 15, 20))).toBe('2026-10-20')
  })

  it('refuses today even early in the morning', () => {
    expect(isBookableDate('2026-10-19', new Date(2026, 9, 19, 0, 1))).toBe(false)
  })

  it('refuses a past date', () => {
    expect(isBookableDate('2026-10-18', new Date(2026, 9, 19))).toBe(false)
  })

  it('accepts tomorrow', () => {
    expect(isBookableDate('2026-10-20', new Date(2026, 9, 19))).toBe(true)
  })

  it('refuses an empty date', () => {
    expect(isBookableDate('', new Date(2026, 9, 19))).toBe(false)
  })
})

describe('takenHours', () => {
  const bookings = [
    { venueName: 'Futsal A', date: '2026-10-19', startTime: '09:00', endTime: '12:00' },
    // A different venue on the same day must not block this one.
    { venueName: 'Futsal B', date: '2026-10-19', startTime: '09:00', endTime: '11:00' },
    // The same venue on a different day must not block it either.
    { venueName: 'Futsal A', date: '2026-10-20', startTime: '09:00', endTime: '11:00' },
  ]

  it('collects the booked hours for that venue and day only', () => {
    expect([...takenHours(bookings, 'Futsal A', '2026-10-19')].sort((a, b) => a - b)).toEqual([
      9, 10, 11,
    ])
  })

  it('keeps the end hour free', () => {
    // 09:00-12:00 occupies 9, 10, 11 — hour 12 is the next booking's start.
    expect(takenHours(bookings, 'Futsal A', '2026-10-19').has(12)).toBe(false)
  })

  it('is empty when nothing matches', () => {
    expect(takenHours(bookings, 'Futsal A', '2026-10-21').size).toBe(0)
  })
})

describe('hasConflict', () => {
  const taken = new Set([17, 18, 19])

  it('rejects a range that overlaps', () => {
    expect(hasConflict(taken, 16, 18)).toBe(true)
  })

  it('accepts a range that ends where a taken hour starts', () => {
    // 14:00-17:00 must be bookable even though 17 is taken: the range is
    // [start, end), so the end hour is the next visit's, not ours.
    expect(hasConflict(taken, 14, 17)).toBe(false)
  })

  it('accepts a range that starts where a taken hour ends', () => {
    expect(hasConflict(taken, 20, 22)).toBe(false)
  })

  it('rejects a single taken hour', () => {
    expect(hasConflict(taken, 18, 19)).toBe(true)
  })

  it('accepts an empty range', () => {
    expect(hasConflict(taken, 18, 18)).toBe(false)
  })
})
