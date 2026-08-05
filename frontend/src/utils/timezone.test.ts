import { afterEach, describe, expect, it } from 'vitest'

import {
  DEFAULT_DISPLAY_TZ,
  dayOffset,
  formatDate,
  formatDateTime,
  formatTime,
  fromDisplayTz,
  getDisplayTz,
  isValidTimeZone,
  isoToDatetimeLocal,
  setDisplayTz,
  toDisplayTz,
} from './timezone'

// Asia/Tashkent is a fixed UTC+5 (no DST). 09:00 UTC → 14:00 Tashkent.
// `format(..., { timeZone })` is deterministic regardless of the runner's TZ.
const ISO = '2026-06-01T09:00:00Z'

// Module-level zone leaks between tests unless restored.
afterEach(() => setDisplayTz(DEFAULT_DISPLAY_TZ))

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

describe('toDisplayTz', () => {
  it('returns a Date for a valid ISO string', () => {
    expect(toDisplayTz(ISO)).toBeInstanceOf(Date)
  })
})

describe('setDisplayTz — зона показа меняет вывод форматтеров (ARCH-137 B6)', () => {
  it('formatTime follows the configured zone', () => {
    setDisplayTz('Europe/London')
    // 09:00Z в июне = 10:00 BST (Лондон с DST).
    expect(formatTime(ISO)).toBe('10:00')
    expect(getDisplayTz()).toBe('Europe/London')
  })

  it('isoToDatetimeLocal follows the configured zone', () => {
    setDisplayTz('America/New_York')
    // 09:00Z в июне = 05:00 EDT.
    expect(isoToDatetimeLocal(ISO)).toBe('2026-06-01T05:00')
  })
})

describe('fromDisplayTz', () => {
  it('interprets a datetime-local string as display-zone wall clock', () => {
    // 13:00 Ташкента = 08:00Z.
    expect(fromDisplayTz('2026-06-05T13:00')).toBe('2026-06-05T08:00:00.000Z')
  })

  it('round-trips with isoToDatetimeLocal', () => {
    for (const iso of [
      '2026-06-05T08:00:00.000Z',
      '2026-08-04T20:30:00.000Z', // 01:30 следующего дня в Ташкенте
      '2026-12-31T19:00:00.000Z', // полночь Нового года в Ташкенте
    ]) {
      expect(fromDisplayTz(isoToDatetimeLocal(iso))).toBe(iso)
    }
  })

  it('accepts a display-zone carrier Date (day-window building block)', () => {
    // Carrier «2026-08-02 00:00 стенки объекта» → инстант 19:00Z накануне.
    const carrier = toDisplayTz('2026-08-01T19:00:00.000Z')
    expect(fromDisplayTz(carrier)).toBe('2026-08-01T19:00:00.000Z')
  })
})

describe('isValidTimeZone', () => {
  it('accepts IANA zones and rejects garbage', () => {
    expect(isValidTimeZone('Asia/Tashkent')).toBe(true)
    expect(isValidTimeZone('Europe/London')).toBe(true)
    expect(isValidTimeZone('Not/AZone')).toBe(false)
    expect(isValidTimeZone('')).toBe(false)
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

describe('isoToDatetimeLocal', () => {
  it('produces a Tashkent wall-clock datetime-local value', () => {
    // 08:00Z = 13:00 Tashkent
    expect(isoToDatetimeLocal('2026-06-05T08:00:00Z')).toBe('2026-06-05T13:00')
  })
  it('rolls the date forward when Tashkent offset crosses midnight', () => {
    // 20:00Z = 01:00 Tashkent next day
    expect(isoToDatetimeLocal('2026-06-05T20:00:00Z')).toBe('2026-06-06T01:00')
  })
})
