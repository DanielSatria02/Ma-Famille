import { describe, expect, it } from 'vitest'

import { addDays, formatHour, parseIsoDate, toIsoDate } from './date.js'

describe('toIsoDate', () => {
  // The trap: `new Date().toISOString()` is UTC, so an evening in a UTC+7
  // country lands on the previous day. The helper must use local parts.
  it('uses local time, not UTC', () => {
    const evening = new Date(2026, 9, 19, 23, 30)
    expect(toIsoDate(evening)).toBe('2026-10-19')
  })

  it('pads single-digit months and days', () => {
    expect(toIsoDate(new Date(2026, 0, 5))).toBe('2026-01-05')
  })

  it('round-trips through parseIsoDate', () => {
    const original = new Date(2026, 11, 31)
    expect(parseIsoDate(toIsoDate(original))).toEqual(original)
  })
})

describe('addDays', () => {
  it('crosses a month boundary', () => {
    expect(toIsoDate(addDays(new Date(2026, 9, 31), 1))).toBe('2026-11-01')
  })

  it('crosses a year boundary', () => {
    expect(toIsoDate(addDays(new Date(2026, 11, 31), 1))).toBe('2027-01-01')
  })

  it('handles negative offsets', () => {
    expect(toIsoDate(addDays(new Date(2026, 0, 1), -1))).toBe('2025-12-31')
  })

  // DST shifts change the clock, never the calendar day.
  it('keeps the date when the clock shifts', () => {
    const before = addDays(new Date(2026, 2, 28), 1)
    expect([before.getDate(), before.getMonth() + 1]).toEqual([29, 3])
  })
})

describe('formatHour', () => {
  it('pads to two digits', () => {
    expect(formatHour(9)).toBe('09:00')
  })

  it('leaves two-digit hours alone', () => {
    expect(formatHour(23)).toBe('23:00')
  })
})
