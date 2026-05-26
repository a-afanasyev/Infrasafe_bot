import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent, formatTime } from '../../utils/timezone'
import {
  executorKey,
  isSameDay,
  isWeekend,
  shiftTypeColor,
  startOfDay,
  weekDays,
} from '../../utils/shiftWeek'
import EmptyState from '../shared/EmptyState'
import { cn } from '@/lib/utils'

interface Props {
  shifts: ShiftBrief[]
  weekAnchor: Date
  onShiftClick: (shift: ShiftBrief) => void
}

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

type DaySegment = {
  shift: ShiftBrief
  /** Local startOfDay for the day this segment lives in. */
  day: Date
  startHour: number
  endHour: number // exclusive; values >24 mean "still going at end of day"
  part: 'full' | 'start' | 'end'
}

/**
 * Slice a shift into per-day segments. Overnight (20:00 → 08:00) yields two:
 * one in the start day going to 24, and one starting at 0 in the next day.
 * Same-day shifts return a single segment.
 */
function shiftSegmentsByDay(shift: ShiftBrief): DaySegment[] {
  const start = toTashkent(shift.start_time)
  if (!shift.end_time) {
    return [{
      shift,
      day: startOfDay(start),
      startHour: start.getHours(),
      endHour: start.getHours() + 1,
      part: 'full',
    }]
  }
  const end = toTashkent(shift.end_time)

  const startDay = startOfDay(start)
  const endDay = startOfDay(end)
  const startHour = start.getHours() + start.getMinutes() / 60
  const endHour = end.getHours() + end.getMinutes() / 60

  if (isSameDay(start, end) || endDay.getTime() === startDay.getTime()) {
    return [{
      shift,
      day: startDay,
      startHour,
      endHour: Math.max(endHour, startHour + 0.5),
      part: 'full',
    }]
  }

  // Multi-day (incl. overnight): tail in start day until 24h, head in next.
  const headSegment: DaySegment = {
    shift,
    day: startDay,
    startHour,
    endHour: 24,
    part: 'start',
  }
  const tailSegment: DaySegment = {
    shift,
    day: endDay,
    startHour: 0,
    endHour: Math.max(endHour, 0.5),
    part: 'end',
  }
  return [headSegment, tailSegment]
}

function getInitials(name: string | null): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
}

const NAME_GRADIENTS = [
  'linear-gradient(135deg,#00d4aa,#0099ff)',
  'linear-gradient(135deg,#8b5cf6,#06b6d4)',
  'linear-gradient(135deg,#f59e0b,#ef4444)',
  'linear-gradient(135deg,#10b981,#3b82f6)',
  'linear-gradient(135deg,#ec4899,#8b5cf6)',
]

function getGradient(name: string | null): string {
  if (!name) return NAME_GRADIENTS[0]
  const hash = name.split('').reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  return NAME_GRADIENTS[hash % NAME_GRADIENTS.length]
}

export default function WeekResourceGrid({ shifts, weekAnchor, onShiftClick }: Props) {
  const { t } = useTranslation()

  if (shifts.length === 0) {
    return (
      <EmptyState
        icon={'\u{1F4C5}'}
        title={t('shifts.empty.week')}
        subtitle={t('shifts.noShiftsDesc')}
      />
    )
  }

  const days = weekDays(weekAnchor)
  const today = new Date()

  // Group shifts by executor; preserve insertion order so the same shift list
  // produces a stable row order across re-renders (sorted by first start_time).
  // Memoize the heavy bucket-and-segment work — `useShiftsWebSocket` triggers
  // frequent parent re-renders and the segment math is O(N).
  type ExecutorRow = {
    key: string
    name: string
    primarySpec: string | null
    segments: DaySegment[]
    firstStartMs: number
  }
  const executors = useMemo(() => {
    const executorMap = new Map<string, ExecutorRow>()
    for (const shift of shifts) {
      const key = executorKey(shift)
      if (!executorMap.has(key)) {
        executorMap.set(key, {
          key,
          name: shift.executor_name ?? key,
          primarySpec: (shift.specialization_focus ?? [])[0] ?? null,
          segments: [],
          firstStartMs: new Date(shift.start_time).getTime(),
        })
      }
      const row = executorMap.get(key)!
      row.segments.push(...shiftSegmentsByDay(shift))
      row.firstStartMs = Math.min(row.firstStartMs, new Date(shift.start_time).getTime())
      if (!row.primarySpec && (shift.specialization_focus ?? []).length > 0) {
        row.primarySpec = shift.specialization_focus![0]
      }
    }
    return Array.from(executorMap.values()).sort(
      (a, b) => a.firstStartMs - b.firstStartMs,
    )
  }, [shifts])

  return (
    <div className="overflow-x-auto">
      <div
        // 180px sticky name col + 7 equal day cols. minWidth picks ~1000px so
        // each day fits ≥110px before forcing horizontal scroll on small screens.
        className="grid"
        style={{
          gridTemplateColumns: '180px repeat(7, minmax(110px, 1fr))',
          minWidth: '900px',
        }}
      >
        {/* Header: name | Mon..Sun */}
        <div className="sticky left-0 z-[3] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-2.5 text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center">
          {t('shifts.executorLabel')}
        </div>
        {days.map((day, idx) => {
          const isToday = isSameDay(day, today)
          return (
            <div
              key={day.toISOString()}
              className={cn(
                'border-b border-border-default py-2 text-center text-[11px] font-semibold',
                idx < 6 && 'border-r border-r-[var(--border-subtle,var(--border))]',
                isWeekend(day) && 'bg-[rgba(255,255,255,0.02)]',
                isToday ? 'text-accent bg-accent-dim' : 'text-text-muted',
              )}
            >
              <div className="font-[var(--font-display)] uppercase tracking-wide">
                {t(`days.short.${DAY_KEYS[idx]}`)}
              </div>
              <div className="font-[var(--font-mono)] text-[13px] mt-0.5 text-text-primary">
                {day.getDate()}
              </div>
            </div>
          )
        })}

        {/* Body rows: executor + 7 day cells */}
        {executors.map(row => (
          <div key={row.key} className="contents">
            <div className="sticky left-0 z-[2] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-2 flex items-center gap-2 min-h-[56px]">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0"
                style={{ background: getGradient(row.name) }}
              >
                {getInitials(row.name)}
              </div>
              <div className="flex flex-col overflow-hidden">
                <span className="text-xs font-semibold text-text-primary truncate">
                  {row.name}
                </span>
                {row.primarySpec && (
                  <span className="text-[10px] text-text-muted truncate">
                    {row.primarySpec}
                  </span>
                )}
              </div>
            </div>
            {days.map((day, idx) => {
              const isToday = isSameDay(day, today)
              const cellSegments = row.segments.filter(s =>
                isSameDay(s.day, day),
              )
              return (
                <DayCell
                  key={day.toISOString()}
                  day={day}
                  segments={cellSegments}
                  hasRightBorder={idx < 6}
                  isWeekendDay={isWeekend(day)}
                  isToday={isToday}
                  onShiftClick={onShiftClick}
                />
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

interface DayCellProps {
  day: Date
  segments: DaySegment[]
  hasRightBorder: boolean
  isWeekendDay: boolean
  isToday: boolean
  onShiftClick: (shift: ShiftBrief) => void
}

function DayCell({
  segments,
  hasRightBorder,
  isWeekendDay,
  isToday,
  onShiftClick,
}: DayCellProps) {
  const { t } = useTranslation()
  return (
    <div
      className={cn(
        'border-b border-border-default relative min-h-[56px] p-1.5 flex flex-col gap-1',
        hasRightBorder && 'border-r border-r-[rgba(255,255,255,0.04)]',
        isWeekendDay && 'bg-[rgba(255,255,255,0.02)]',
        isToday && 'bg-accent-dim/40',
      )}
    >
      {segments.map((seg, idx) => {
        const color = shiftTypeColor(seg.shift.shift_type)
        const isPartial = seg.part !== 'full'
        // Visual width within cell — proportional to hours covered (clipped 0..24).
        const span = Math.max(0.5, Math.min(seg.endHour, 24) - seg.startHour)
        const widthPct = Math.max(15, Math.min(100, (span / 24) * 100))
        const leftPct = Math.max(0, Math.min(100, (seg.startHour / 24) * 100))
        const label =
          seg.shift.start_time && seg.shift.end_time
            ? `${formatTime(seg.shift.start_time)} – ${formatTime(seg.shift.end_time)}`
            : formatTime(seg.shift.start_time)
        return (
          <button
            key={`${seg.shift.id}-${idx}-${seg.part}`}
            type="button"
            onClick={() => onShiftClick(seg.shift)}
            title={`${label} · ${t(`shiftStatus.${seg.shift.status}`, seg.shift.status)}`}
            className="relative h-[18px] rounded-[5px] flex items-center justify-center text-[10px] font-semibold px-1 cursor-pointer transition-colors duration-150"
            style={{
              background: `${color}22`,
              border: `1px solid ${color}66`,
              color,
              // Offset within the cell so the bar sits where the shift starts
              // on the day's 24h axis — gives a rough hour-position hint while
              // staying within the day cell.
              marginLeft: `${leftPct * 0.85}%`,
              width: `${widthPct}%`,
            }}
          >
            {isPartial && (
              <span
                aria-hidden
                className="absolute -left-1 top-1/2 -translate-y-1/2 font-[var(--font-mono)] text-[10px]"
                style={{ color }}
              >
                {seg.part === 'end' ? '↪' : '↩'}
              </span>
            )}
            <span className="truncate font-[var(--font-mono)] tracking-tight">
              {label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
