import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent } from '../../utils/timezone'

export interface ShiftBlock {
  shift: ShiftBrief
  colStart: number  // 1-indexed grid column (header is col 1, hour 0 is col 2)
  colSpan: number
  isOvernight: boolean
  part: 'full' | 'start' | 'end'
}

// Day-number key in the display tz (Tashkent), so a shift can be compared
// against the viewed calendar day regardless of how many days it spans.
function dayKey(d: Date): number {
  return d.getFullYear() * 10000 + d.getMonth() * 100 + d.getDate()
}

/**
 * Blocks for ONE shift on the viewed `date`, clipped to that day's [00:00, 24:00].
 * A shift that crosses midnight (e.g. a 24h shift 13:00→13:00) is fetched for
 * every day it overlaps and renders the visible portion on each: 13:00–24:00 on
 * the start day, 00:00–13:00 on the end day, a full row on any day in between.
 */
export function computeBlocks(shift: ShiftBrief, date: Date): ShiftBlock[] {
  const start = toTashkent(shift.start_time)
  const vd = dayKey(date)
  const sd = dayKey(start)

  if (!shift.end_time) {
    // Open shift — only on its start day, single cell at the start hour.
    if (sd !== vd) return []
    const startHour = start.getHours()
    return [{ shift, colStart: startHour + 2, colSpan: 1, isOvernight: false, part: 'full' }]
  }

  const end = toTashkent(shift.end_time)
  const ed = dayKey(end)

  // Shift doesn't overlap the viewed day at all.
  if (sd > vd || ed < vd) return []

  // Visible window on the viewed day, in fractional hours [0..24].
  const fromHour = sd < vd ? 0 : start.getHours() + start.getMinutes() / 60
  const toHour = ed > vd ? 24 : end.getHours() + end.getMinutes() / 60
  if (toHour - fromHour <= 0) return []  // zero-length on this day (e.g. end exactly at 00:00)

  const colStart = Math.floor(fromHour) + 2
  const colSpanRaw = Math.ceil(toHour) - Math.floor(fromHour)
  const colSpan = Math.max(1, Math.min(colSpanRaw, 26 - colStart))
  return [{
    shift,
    colStart,
    colSpan,
    isOvernight: sd !== ed,
    part: sd === ed ? 'full' : (sd === vd ? 'start' : 'end'),
  }]
}
