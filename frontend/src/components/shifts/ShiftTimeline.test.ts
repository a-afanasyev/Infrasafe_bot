import { describe, it, expect } from 'vitest'
import { computeBlocks } from './shiftTimelineBlocks'
import type { ShiftBrief } from '../../hooks/useShifts'

// Grid columns: header is col 1, hour 0 is col 2 → colStart = floor(hour) + 2.
// Tashkent is UTC+5: 08:00Z = 13:00 Tashkent.

function shift(overrides: Partial<ShiftBrief>): ShiftBrief {
  return {
    id: 67,
    user_id: 1,
    executor_name: 'Andrey Afanasyev',
    status: 'planned',
    shift_type: 'regular',
    start_time: '2026-06-05T08:00:00Z',
    end_time: '2026-06-06T08:00:00Z',
    max_requests: 20,
    current_request_count: 0,
    ...overrides,
  } as ShiftBrief
}

describe('computeBlocks — 24h shift crossing midnight (13:00→13:00 Tashkent)', () => {
  const s = shift({})

  it('renders 13:00→24:00 on the START day (not a 1h block)', () => {
    const blocks = computeBlocks(s, new Date(2026, 5, 5))
    expect(blocks).toHaveLength(1)
    expect(blocks[0].colStart).toBe(15) // hour 13 → col 15
    expect(blocks[0].colSpan).toBe(11)  // 13:00..24:00 = 11 hours
    expect(blocks[0].part).toBe('start')
  })

  it('renders 00:00→13:00 on the END day', () => {
    const blocks = computeBlocks(s, new Date(2026, 5, 6))
    expect(blocks).toHaveLength(1)
    expect(blocks[0].colStart).toBe(2)  // hour 0 → col 2
    expect(blocks[0].colSpan).toBe(13)  // 00:00..13:00 = 13 hours
    expect(blocks[0].part).toBe('end')
  })

  it('is not rendered on an unrelated day', () => {
    expect(computeBlocks(s, new Date(2026, 5, 7))).toHaveLength(0)
  })
})

describe('computeBlocks — same-day shift', () => {
  it('spans start→end within the day', () => {
    // 03:00Z..11:00Z = 08:00..16:00 Tashkent
    const s = shift({ start_time: '2026-06-05T03:00:00Z', end_time: '2026-06-05T11:00:00Z' })
    const blocks = computeBlocks(s, new Date(2026, 5, 5))
    expect(blocks).toHaveLength(1)
    expect(blocks[0].colStart).toBe(10) // hour 8 → col 10
    expect(blocks[0].colSpan).toBe(8)   // 8 hours
    expect(blocks[0].part).toBe('full')
  })
})

describe('computeBlocks — open shift (no end)', () => {
  it('shows a single cell on its start day only', () => {
    const s = shift({ end_time: null })
    const onDay = computeBlocks(s, new Date(2026, 5, 5))
    expect(onDay).toHaveLength(1)
    expect(onDay[0].colSpan).toBe(1)
    expect(computeBlocks(s, new Date(2026, 5, 6))).toHaveLength(0)
  })
})
