import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent } from '../../utils/timezone'
import {
  executorKey,
  isSameDay,
  isWeekend,
  monthWeekRows,
} from '../../utils/shiftWeek'
import { cn } from '@/lib/utils'

/**
 * Month-level calendar-heatmap: 5–6 ISO-week rows × 7 day columns.
 * Cell colour encodes the day's coverage relative to the target headcount.
 *
 * Coverage = executors-on-shift-during-day / coverage_target.
 * Without `ShiftSchedule.coverage_percentage` per-row reliably wired,
 * we approximate locally: count distinct executors that have any shift
 * starting (or active) on that day, divided by the `coverageTarget` prop.
 *
 * Click cell → drill into the week containing that day via `onDayClick`.
 */
interface Props {
  shifts: ShiftBrief[]
  monthAnchor: Date
  /** Expected staffed-headcount per day. Defaults to 3 (matches median
   *  ShiftTemplate.max_executors default in the codebase). */
  coverageTarget?: number
  onDayClick: (day: Date) => void
}

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

/**
 * Pre-compute per-day executor sets in one pass over the shifts list.
 * Without this the render-loop calls `toTashkent` twice per shift per day
 * cell — at 600 shifts × 31 days that's ~37k tz conversions per render.
 */
function buildDayCoverage(shifts: ShiftBrief[]): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>()
  for (const shift of shifts) {
    const startTZ = toTashkent(shift.start_time)
    const startDay = new Date(startTZ.getFullYear(), startTZ.getMonth(), startTZ.getDate())
    const endTZ = shift.end_time ? toTashkent(shift.end_time) : null
    const endDay = endTZ
      ? new Date(endTZ.getFullYear(), endTZ.getMonth(), endTZ.getDate())
      : startDay
    const execKey = executorKey(shift)
    const cursor = new Date(startDay)
    while (cursor.getTime() <= endDay.getTime()) {
      const k = dayKey(cursor)
      const set = out.get(k)
      if (set) set.add(execKey)
      else out.set(k, new Set([execKey]))
      cursor.setDate(cursor.getDate() + 1)
    }
  }
  return out
}

function coverageBucket(pct: number): 'low' | 'mid' | 'high' | 'over' {
  if (pct < 0.5) return 'low'
  if (pct < 0.8) return 'mid'
  if (pct <= 1.0) return 'high'
  return 'over'
}

const BUCKET_BG: Record<'low' | 'mid' | 'high' | 'over', string> = {
  low: 'rgba(239,68,68,0.30)',
  mid: 'rgba(245,158,11,0.35)',
  high: 'rgba(var(--accent-rgb),0.40)',
  over: 'rgba(59,130,246,0.50)',
}

const BUCKET_LEGEND = [
  { key: 'low', label: '<50%' },
  { key: 'mid', label: '50–80%' },
  { key: 'high', label: '80–100%' },
  { key: 'over', label: '>100%' },
] as const

export default function CalendarHeatmap({
  shifts,
  monthAnchor,
  coverageTarget = 3,
  onDayClick,
}: Props) {
  const { t } = useTranslation()
  const today = new Date()

  const rows = useMemo(() => monthWeekRows(monthAnchor), [monthAnchor])
  const dayCoverage = useMemo(() => buildDayCoverage(shifts), [shifts])

  return (
    <div className="flex flex-col gap-2">
      {/* Day-of-week header */}
      <div
        className="grid"
        style={{ gridTemplateColumns: `48px repeat(7, minmax(36px, 1fr))` }}
      >
        <div />
        {DAY_KEYS.map(key => (
          <div
            key={key}
            className="text-center text-[10px] font-[var(--font-display)] uppercase tracking-wider text-text-muted py-1"
          >
            {t(`days.short.${key}`)}
          </div>
        ))}
      </div>

      {/* Week rows */}
      {rows.map((row, weekIdx) => (
        <div
          key={row[0].toISOString()}
          className="grid"
          style={{ gridTemplateColumns: `48px repeat(7, minmax(36px, 1fr))` }}
        >
          <div className="flex items-center justify-end pr-2 text-[10px] text-text-muted font-[var(--font-mono)]">
            W{weekIdx + 1}
          </div>
          {row.map(day => {
            const inMonth =
              day.getMonth() === monthAnchor.getMonth() &&
              day.getFullYear() === monthAnchor.getFullYear()
            if (!inMonth) {
              return (
                <div
                  key={day.toISOString()}
                  className="h-8 rounded-sm bg-[rgba(255,255,255,0.02)]"
                />
              )
            }
            const headcount = dayCoverage.get(dayKey(day))?.size ?? 0
            const pct = coverageTarget > 0 ? headcount / coverageTarget : 0
            const bucket = coverageBucket(pct)
            const isToday = isSameDay(day, today)
            return (
              <button
                key={day.toISOString()}
                type="button"
                onClick={() => onDayClick(day)}
                title={`${day.getDate()}.${day.getMonth() + 1} · ${headcount}/${coverageTarget} (${Math.round(pct * 100)}%)`}
                className={cn(
                  'h-8 rounded-sm flex items-center justify-center text-[10px] font-semibold transition-transform hover:scale-[1.05] cursor-pointer relative',
                  isWeekend(day) && 'opacity-95',
                  isToday && 'ring-1 ring-accent',
                )}
                style={{ background: BUCKET_BG[bucket], color: 'rgba(255,255,255,0.85)' }}
              >
                <span className="font-[var(--font-mono)]">{day.getDate()}</span>
                <span className="absolute bottom-0.5 right-1 text-[9px] opacity-80">
                  {headcount}
                </span>
              </button>
            )
          })}
        </div>
      ))}

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 pt-2 px-1 text-[11px] text-text-muted">
        {BUCKET_LEGEND.map(item => (
          <span key={item.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="w-3.5 h-3.5 rounded-[3px]"
              style={{ background: BUCKET_BG[item.key] }}
            />
            {item.label}
          </span>
        ))}
        <span className="ml-2 opacity-80">
          {t('shifts.heatmapSummary', {
            shifts: shifts.length,
            hours: shifts.reduce((acc, s) => {
              if (!s.end_time) return acc
              const hrs = (new Date(s.end_time).getTime() - new Date(s.start_time).getTime()) / 3_600_000
              return acc + Math.max(0, hrs)
            }, 0).toFixed(0),
          })}
        </span>
      </div>
    </div>
  )
}
