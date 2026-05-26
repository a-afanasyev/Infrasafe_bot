import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent } from '../../utils/timezone'
import {
  daysInMonth,
  isSameDay,
  isWeekend,
  shiftTypeColor,
  specColor,
} from '../../utils/shiftWeek'
import EmptyState from '../shared/EmptyState'
import { cn } from '@/lib/utils'

import { UNSPECIFIED_KEY } from './SpecializationSidebar'

interface Props {
  shifts: ShiftBrief[]
  monthAnchor: Date
  /**
   * Selected sidebar entry. `null` = "Все" (no filter), empty string `""`
   * = "Универсалы" (specialization_focus is null or empty), any other
   * string = match that specialization.
   */
  selectedSpec: string | null
  onShiftClick: (shift: ShiftBrief) => void
}

function shiftMatchesSpec(shift: ShiftBrief, selected: string | null): boolean {
  if (selected === null) return true
  const specs = shift.specialization_focus ?? []
  if (selected === '' || selected === UNSPECIFIED_KEY) {
    return specs.length === 0
  }
  return specs.includes(selected)
}

interface ExecutorRow {
  key: string
  name: string
  primarySpec: string | null
  shiftsByDay: Map<number, ShiftBrief[]> // day-of-month → shifts that start that day
  totalShifts: number
  totalHours: number
}

function shiftHours(shift: ShiftBrief): number {
  if (!shift.end_time) return 0
  const ms = new Date(shift.end_time).getTime() - new Date(shift.start_time).getTime()
  return Math.max(0, ms / 3_600_000)
}

export default function MonthResourceGrid({
  shifts,
  monthAnchor,
  selectedSpec,
  onShiftClick,
}: Props) {
  const { t } = useTranslation()
  const days = useMemo(() => daysInMonth(monthAnchor), [monthAnchor])
  const today = new Date()

  const executors = useMemo(() => {
    const filtered = shifts.filter(s => shiftMatchesSpec(s, selectedSpec))
    const map = new Map<string, ExecutorRow>()
    for (const shift of filtered) {
      const key =
        shift.executor_name || (shift.user_id ? `user_${shift.user_id}` : `shift_${shift.id}`)
      let row = map.get(key)
      if (!row) {
        row = {
          key,
          name: shift.executor_name ?? key,
          primarySpec: (shift.specialization_focus ?? [])[0] ?? null,
          shiftsByDay: new Map(),
          totalShifts: 0,
          totalHours: 0,
        }
        map.set(key, row)
      }
      const startTZ = toTashkent(shift.start_time)
      const dayOfMonth = startTZ.getDate()
      // Only assign to the day if it belongs to the visible month — multi-day
      // overflow into next month is out of scope for the month-grid (it's a
      // condensed planner view, not the per-day timeline).
      if (
        startTZ.getMonth() === monthAnchor.getMonth() &&
        startTZ.getFullYear() === monthAnchor.getFullYear()
      ) {
        const existing = row.shiftsByDay.get(dayOfMonth) ?? []
        existing.push(shift)
        row.shiftsByDay.set(dayOfMonth, existing)
      }
      row.totalShifts += 1
      row.totalHours += shiftHours(shift)
      if (!row.primarySpec && (shift.specialization_focus ?? []).length > 0) {
        row.primarySpec = shift.specialization_focus![0]
      }
    }
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [shifts, selectedSpec, monthAnchor])

  if (executors.length === 0) {
    return (
      <EmptyState
        icon={'\u{1F4C6}'}
        title={t('shifts.empty.month')}
        subtitle={t('shifts.noShiftsDesc')}
      />
    )
  }

  return (
    <div className="overflow-x-auto">
      <div
        // Sticky 180px name column + N day cells of ≥28px (squareish).
        className="grid"
        style={{
          gridTemplateColumns: `180px repeat(${days.length}, minmax(28px, 1fr)) 96px`,
          minWidth: `${180 + days.length * 28 + 96}px`,
        }}
      >
        {/* Header row: name | 1..30 | total */}
        <div className="sticky left-0 z-[3] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-2.5 text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center">
          {t('shifts.executorLabel')}
        </div>
        {days.map((day, idx) => {
          const isToday = isSameDay(day, today)
          return (
            <div
              key={day.toISOString()}
              className={cn(
                'border-b border-border-default py-1 text-center text-[10px] font-semibold relative',
                idx < days.length - 1 && 'border-r border-r-[var(--border-subtle,var(--border))]',
                isWeekend(day) && 'bg-[rgba(255,255,255,0.02)]',
                isToday ? 'text-accent bg-accent-dim' : 'text-text-muted',
              )}
            >
              <span className="font-[var(--font-mono)]">{day.getDate()}</span>
            </div>
          )
        })}
        <div className="border-b border-border-default px-2 py-2 text-[10px] font-bold text-text-muted uppercase tracking-wider text-right">
          {/* compact "Σ" header — translation handled inside label */}
          {'Σ'}
        </div>

        {/* Body rows */}
        {executors.map(row => (
          <div key={row.key} className="contents">
            <div className="sticky left-0 z-[2] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-1.5 flex items-center gap-2 min-h-[34px]">
              <span
                aria-hidden
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: row.primarySpec ? specColor(row.primarySpec) : 'var(--text-muted)' }}
              />
              <span className="text-xs font-semibold text-text-primary truncate">
                {row.name}
              </span>
            </div>
            {days.map((day, idx) => {
              const dayShifts = row.shiftsByDay.get(day.getDate()) ?? []
              return (
                <DayDot
                  key={day.toISOString()}
                  day={day}
                  shifts={dayShifts}
                  hasRightBorder={idx < days.length - 1}
                  isWeekendDay={isWeekend(day)}
                  isToday={isSameDay(day, today)}
                  onShiftClick={onShiftClick}
                />
              )
            })}
            <div className="border-b border-border-default px-2 py-1.5 text-right text-[10px] text-text-muted font-[var(--font-mono)]">
              <div className="text-text-primary font-semibold">{row.totalShifts}</div>
              <div>{Math.round(row.totalHours)}ч</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

interface DayDotProps {
  day: Date
  shifts: ShiftBrief[]
  hasRightBorder: boolean
  isWeekendDay: boolean
  isToday: boolean
  onShiftClick: (shift: ShiftBrief) => void
}

function DayDot({ shifts, hasRightBorder, isWeekendDay, isToday, onShiftClick }: DayDotProps) {
  const { t } = useTranslation()
  if (shifts.length === 0) {
    return (
      <div
        className={cn(
          'border-b border-border-default min-h-[34px]',
          hasRightBorder && 'border-r border-r-[rgba(255,255,255,0.04)]',
          isWeekendDay && 'bg-[rgba(255,255,255,0.02)]',
          isToday && 'bg-accent-dim/40',
        )}
      />
    )
  }
  const first = shifts[0]
  const color = shiftTypeColor(first.shift_type)
  const isHalf = shifts.length > 1
  const tooltip = shifts
    .map(s => {
      const start = new Date(s.start_time).toISOString().split('T')[1]?.slice(0, 5) ?? ''
      const end = s.end_time ? new Date(s.end_time).toISOString().split('T')[1]?.slice(0, 5) ?? '' : '—'
      return `${start}–${end} (${t(`shiftStatus.${s.status}`, s.status)})`
    })
    .join('\n')

  return (
    <div
      className={cn(
        'border-b border-border-default min-h-[34px] flex items-center justify-center',
        hasRightBorder && 'border-r border-r-[rgba(255,255,255,0.04)]',
        isWeekendDay && 'bg-[rgba(255,255,255,0.02)]',
        isToday && 'bg-accent-dim/40',
      )}
    >
      <button
        type="button"
        title={tooltip}
        onClick={() => onShiftClick(first)}
        className="w-4 h-4 rounded-full cursor-pointer transition-transform hover:scale-110 relative"
        style={{
          background: color,
          boxShadow: `0 0 0 1px ${color}44`,
        }}
      >
        {isHalf && (
          <span
            aria-hidden
            className="absolute -top-1 -right-1 bg-bg-card text-text-primary text-[8px] font-[var(--font-mono)] font-bold w-3 h-3 rounded-full flex items-center justify-center border border-border-default"
          >
            {shifts.length}
          </span>
        )}
      </button>
    </div>
  )
}
