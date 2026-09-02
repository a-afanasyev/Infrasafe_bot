import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { usePersonName } from '../../hooks/usePersonName'

import type { ShiftBrief } from '../../hooks/useShifts'
import { useResizableColumn } from '../../hooks/useResizableColumn'
import { formatTime, toDisplayTz, dayOffset } from '../../utils/timezone'
import {
  daysInMonth,
  executorKey,
  isSameDay,
  isWeekend,
  shiftTypeColor,
  specColor,
} from '../../utils/shiftWeek'
import EmptyState from '../shared/EmptyState'
import { cn } from '@/lib/utils'

interface Props {
  /** Смены УЖЕ отфильтрованы полосой специализаций на уровне страницы. */
  shifts: ShiftBrief[]
  monthAnchor: Date
  onShiftClick: (shift: ShiftBrief) => void
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
  onShiftClick,
}: Props) {
  const { t } = useTranslation()
  const { name: personName } = usePersonName()
  const days = useMemo(() => daysInMonth(monthAnchor), [monthAnchor])
  const today = new Date()
  // Автоподбор под самое длинное ФИО (жалоба владельца: дефолт снова резал
  // имена). ~6.9px/символ для 12px semibold-капса + точка/бейдж/отступы.
  const autoNameW = useMemo(() => {
    const longest = shifts.reduce(
      (acc, s) => Math.max(acc, (s.executor_name ?? '').length), 0)
    return Math.round(longest * 6.9) + 118
  }, [shifts])
  // Один storageKey с недельным видом — ширина колонки ФИО общая для обоих.
  const { width: nameColW, handleProps } = useResizableColumn(
    'uk.shifts.nameColW', 220, 140, 440, autoNameW)

  const executors = useMemo(() => {
    const map = new Map<string, ExecutorRow>()
    for (const shift of shifts) {
      const key = executorKey(shift)
      let row = map.get(key)
      if (!row) {
        row = {
          key,
          name: personName(shift.executor_name, key),
          primarySpec: (shift.specialization_focus ?? [])[0] ?? null,
          shiftsByDay: new Map(),
          totalShifts: 0,
          totalHours: 0,
        }
        map.set(key, row)
      }
      const startTZ = toDisplayTz(shift.start_time)
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
  }, [shifts, monthAnchor, personName])

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
        // Sticky (растягиваемая) колонка ФИО + N day cells of ≥28px (squareish).
        className="grid"
        style={{
          gridTemplateColumns: `${nameColW}px repeat(${days.length}, minmax(28px, 1fr))`,
          minWidth: `${nameColW + days.length * 28}px`,
        }}
      >
        {/* Header row: name | 1..30 */}
        <div className="sticky left-0 z-[3] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-2.5 text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center relative">
          {t('shifts.executorLabel')}
          {/* Ручка ресайза: тянется мышью/пальцем, ширина сохраняется. */}
          <div
            {...handleProps}
            role="separator"
            aria-orientation="vertical"
            aria-label={t('shifts.resizeColumn')}
            title={t('shifts.resizeColumn')}
            className="absolute right-0 top-0 h-full w-2 cursor-col-resize touch-none hover:bg-accent/40 active:bg-accent/60"
          />
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
        {/* Body rows */}
        {executors.map(row => (
          <div key={row.key} className="contents">
            <div className="sticky left-0 z-[2] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-1.5 flex items-center gap-2 min-h-[34px]">
              <span
                aria-hidden
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: row.primarySpec ? specColor(row.primarySpec) : 'var(--text-muted)' }}
              />
              <span className="text-xs font-semibold text-text-primary truncate" title={row.name}>
                {row.name}
              </span>
              {/* Итог смен/часов — рядом с ФИО (решение владельца 2026-08-27):
                  раньше жил в далёкой sticky Σ-колонке справа и не читался. */}
              <span
                className="ml-auto shrink-0 text-[10px] text-text-muted font-[var(--font-mono)]"
                title={t('shifts.rowTotalTitle', { shifts: row.totalShifts, hours: Math.round(row.totalHours) })}
              >
                {row.totalShifts}&thinsp;·&thinsp;{Math.round(row.totalHours)}{t('analytics.h')}
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
  // Tooltip times must use the same Tashkent-aware helper the rest of the
  // dashboard uses (formatTime) — raw `toISOString` here would render in
  // UTC and disagree with the times shown in WeekResourceGrid / Timeline.
  const tooltip = shifts
    .map(s => {
      const start = formatTime(s.start_time)
      const off = s.end_time ? dayOffset(s.start_time, s.end_time) : 0
      const end = s.end_time ? `${formatTime(s.end_time)}${off > 0 ? ` ${t('shifts.dayOffset', { n: off })}` : ''}` : '—'
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
