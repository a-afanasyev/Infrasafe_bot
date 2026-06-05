import { describe, expect, it } from 'vitest'

import { formatDate, formatDateTime, formatTime, toTashkent, dayOffset } from './timezone'

// Asia/Tashkent is a fixed UTC+5 (no DST). 09:00 UTC → 14:00 Tashkent.
// `format(..., { timeZone })` is deterministic regardless of the runner's TZ.
const ISO = '2026-06-01T09:00:00Z'

describe('formatTime', () => {
  it('renders Tashkent wall-clock HH:mm', () => {
    expect(formatTime(ISO)).toBe('14:00')
  })
})

describe('formatDate', () => {
  it('renders dd.MM.yyyy in Tashkent', () => {
    expect(formatDate(ISO)).toBe('01.06.2026')
  })
})

describe('formatDateTime', () => {
  it('includes the Tashkent date and time', () => {
    const out = formatDateTime(ISO)
    expect(out).toContain('14:00')
    expect(out).toContain('2026')
    expect(out.startsWith('01')).toBe(true)
  })
})

describe('toTashkent', () => {
  it('returns a Date for a valid ISO string', () => {
    expect(toTashkent(ISO)).toBeInstanceOf(Date)
  })
})

describe('dayOffset', () => {
  it('is 0 for a same-day shift', () => {
    expect(dayOffset('2026-06-05T03:00:00Z', '2026-06-05T12:00:00Z')).toBe(0)
  })
  it('is 1 for a 24h shift crossing midnight (Tashkent)', () => {
    // 08:00 Tashkent (03:00Z) → next day 08:00 Tashkent (next 03:00Z)
    expect(dayOffset('2026-06-05T03:00:00Z', '2026-06-06T03:00:00Z')).toBe(1)
  })
  it('is 1 for a night shift ending next morning', () => {
    // 22:00 → 08:00 next day, in Tashkent (UTC+5): 17:00Z → next 03:00Z
    expect(dayOffset('2026-06-05T17:00:00Z', '2026-06-06T03:00:00Z')).toBe(1)
  })
})
