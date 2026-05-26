import { describe, expect, it } from 'vitest'

import {
  addDays,
  daysInMonth,
  endOfMonth,
  endOfWeek,
  isSameDay,
  isWeekend,
  monthWeekRows,
  shiftTypeColor,
  specColor,
  startOfDay,
  startOfMonth,
  startOfWeek,
  weekDays,
} from './shiftWeek'

const MAY_18_2026 = new Date(2026, 4, 18, 14, 30) // Monday
const MAY_24_2026 = new Date(2026, 4, 24, 0, 0) // Sunday
const MAY_27_2026 = new Date(2026, 4, 27, 9, 0) // Wednesday

describe('startOfDay', () => {
  it('strips time-of-day', () => {
    const d = startOfDay(MAY_18_2026)
    expect(d.getHours()).toBe(0)
    expect(d.getMinutes()).toBe(0)
    expect(d.getSeconds()).toBe(0)
    expect(d.getMilliseconds()).toBe(0)
    expect(d.getDate()).toBe(18)
  })
})

describe('startOfWeek (Monday-anchored)', () => {
  it('returns the same Monday when input is Monday', () => {
    const start = startOfWeek(MAY_18_2026)
    expect(start.getDay()).toBe(1) // Monday
    expect(start.getDate()).toBe(18)
  })

  it('wraps Sunday back to the previous Monday', () => {
    const start = startOfWeek(MAY_24_2026)
    expect(start.getDay()).toBe(1)
    expect(start.getDate()).toBe(18)
  })

  it('walks Wednesday back to the same week Monday', () => {
    const start = startOfWeek(MAY_27_2026)
    expect(start.getDay()).toBe(1)
    expect(start.getDate()).toBe(25)
  })
})

describe('endOfWeek', () => {
  it('is exclusive — exactly 7 days after startOfWeek', () => {
    const start = startOfWeek(MAY_18_2026)
    const end = endOfWeek(MAY_18_2026)
    expect(end.getTime() - start.getTime()).toBe(7 * 24 * 60 * 60 * 1000)
    // exclusive: end day is next Monday (25 May 2026)
    expect(end.getDate()).toBe(25)
    expect(end.getDay()).toBe(1)
  })
})

describe('weekDays', () => {
  it('returns Mon..Sun as 7 ascending Date objects', () => {
    const days = weekDays(MAY_18_2026)
    expect(days.length).toBe(7)
    expect(days[0].getDate()).toBe(18)
    expect(days[0].getDay()).toBe(1) // Mon
    expect(days[6].getDate()).toBe(24)
    expect(days[6].getDay()).toBe(0) // Sun
  })
})

describe('startOfMonth / endOfMonth / daysInMonth', () => {
  it('startOfMonth returns the 1st at 00:00', () => {
    const start = startOfMonth(MAY_18_2026)
    expect(start.getDate()).toBe(1)
    expect(start.getMonth()).toBe(4) // May
    expect(start.getHours()).toBe(0)
  })

  it('endOfMonth is the 1st of next month (exclusive)', () => {
    const end = endOfMonth(MAY_18_2026)
    expect(end.getDate()).toBe(1)
    expect(end.getMonth()).toBe(5) // June
  })

  it('daysInMonth returns 31 dates for May 2026', () => {
    const days = daysInMonth(MAY_18_2026)
    expect(days.length).toBe(31)
    expect(days[0].getDate()).toBe(1)
    expect(days[30].getDate()).toBe(31)
    expect(days.every(d => d.getMonth() === 4)).toBe(true)
  })

  it('daysInMonth returns 28 dates for February 2026 (non-leap)', () => {
    const feb = new Date(2026, 1, 10)
    const days = daysInMonth(feb)
    expect(days.length).toBe(28)
  })

  it('daysInMonth returns 29 dates for February 2028 (leap)', () => {
    const feb = new Date(2028, 1, 10)
    const days = daysInMonth(feb)
    expect(days.length).toBe(29)
  })
})

describe('monthWeekRows', () => {
  it('returns Monday-anchored rows that fully cover May 2026', () => {
    const rows = monthWeekRows(MAY_18_2026)
    // Every row is exactly 7 days.
    rows.forEach(row => expect(row.length).toBe(7))
    // First cell of first row is a Monday on/before May 1.
    expect(rows[0][0].getDay()).toBe(1)
    expect(rows[0][0].getTime()).toBeLessThanOrEqual(new Date(2026, 4, 1).getTime())
    // Last cell of last row is on/after May 31.
    const lastRow = rows[rows.length - 1]
    const lastCell = lastRow[6]
    expect(lastCell.getTime()).toBeGreaterThanOrEqual(new Date(2026, 4, 31).getTime())
    // Between 5 and 6 rows (most months are 5).
    expect(rows.length).toBeGreaterThanOrEqual(5)
    expect(rows.length).toBeLessThanOrEqual(6)
  })
})

describe('addDays', () => {
  it('handles month boundary', () => {
    const d = addDays(new Date(2026, 4, 30), 3)
    expect(d.getMonth()).toBe(5) // June
    expect(d.getDate()).toBe(2)
  })

  it('handles negative offsets', () => {
    const d = addDays(new Date(2026, 4, 2), -3)
    expect(d.getMonth()).toBe(3) // April
    expect(d.getDate()).toBe(29)
  })
})

describe('isSameDay / isWeekend', () => {
  it('isSameDay ignores time-of-day', () => {
    expect(
      isSameDay(new Date(2026, 4, 18, 9, 0), new Date(2026, 4, 18, 23, 0)),
    ).toBe(true)
    expect(
      isSameDay(new Date(2026, 4, 18), new Date(2026, 4, 19)),
    ).toBe(false)
  })

  it('isWeekend matches Sat + Sun', () => {
    expect(isWeekend(new Date(2026, 4, 23))).toBe(true) // Sat
    expect(isWeekend(new Date(2026, 4, 24))).toBe(true) // Sun
    expect(isWeekend(new Date(2026, 4, 18))).toBe(false) // Mon
    expect(isWeekend(new Date(2026, 4, 22))).toBe(false) // Fri
  })
})

describe('shiftTypeColor', () => {
  it('returns regular color for null / unknown', () => {
    const reg = shiftTypeColor(null)
    expect(reg).toBe(shiftTypeColor('regular'))
    expect(reg).toBe(shiftTypeColor('totally-made-up-type'))
  })

  it('maps known types to distinct colors', () => {
    const seen = new Set([
      shiftTypeColor('regular'),
      shiftTypeColor('emergency'),
      shiftTypeColor('overtime'),
      shiftTypeColor('maintenance'),
    ])
    expect(seen.size).toBe(4)
  })
})

describe('specColor', () => {
  it('is deterministic per label', () => {
    expect(specColor('electric')).toBe(specColor('electric'))
    expect(specColor('plumbing')).toBe(specColor('plumbing'))
  })

  it('returns a non-empty hex string', () => {
    const c = specColor('plumbing')
    expect(c).toMatch(/^#[0-9a-fA-F]{6}$/)
  })
})
