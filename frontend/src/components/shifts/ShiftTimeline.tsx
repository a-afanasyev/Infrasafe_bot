import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent, formatTime } from '../../utils/timezone'
import EmptyState from '../shared/EmptyState'
import { cn } from '@/lib/utils'

interface Props {
  shifts: ShiftBrief[]
  date: Date
  onShiftClick: (shift: ShiftBrief) => void
}

const SHIFT_TYPE_COLORS: Record<string, string> = {
  regular: '#3b82f6',
  emergency: '#ef4444',
  overtime: '#f59e0b',
  maintenance: '#8b5cf6',
}

function getInitials(name: string | null): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase()
}

function getGradient(name: string | null): string {
  const gradients = [
    'linear-gradient(135deg,#00d4aa,#0099ff)',
    'linear-gradient(135deg,#8b5cf6,#06b6d4)',
    'linear-gradient(135deg,#f59e0b,#ef4444)',
    'linear-gradient(135deg,#10b981,#3b82f6)',
    'linear-gradient(135deg,#ec4899,#8b5cf6)',
  ]
  if (!name) return gradients[0]
  const hash = name.split('').reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  return gradients[hash % gradients.length]
}

interface ShiftBlock {
  shift: ShiftBrief
  colStart: number  // 1-indexed grid column (header is col 1, hour 0 is col 2)
  colSpan: number
  isOvernight: boolean
  part: 'full' | 'start' | 'end'
}

function computeBlocks(shift: ShiftBrief): ShiftBlock[] {
  const start = toTashkent(shift.start_time)
  const startHour = start.getHours()

  if (!shift.end_time) {
    return [{
      shift,
      colStart: startHour + 2,
      colSpan: 1,
      isOvernight: false,
      part: 'full',
    }]
  }

  const end = toTashkent(shift.end_time)
  const endHour = end.getHours()
  const endMin = end.getMinutes()

  // Effective end hour cell: if minutes > 0, the shift extends into endHour cell
  const effectiveEndHour = endMin > 0 ? endHour : Math.max(endHour - 1, startHour)

  if (effectiveEndHour >= startHour) {
    // Normal (non-overnight)
    const colStart = Math.min(startHour + 2, 25)
    const span = Math.max(1, Math.min(effectiveEndHour - startHour + 1, 24 - startHour))
    const colSpan = Math.max(1, Math.min(span, 26 - colStart))
    return [{
      shift,
      colStart,
      colSpan,
      isOvernight: false,
      part: 'full',
    }]
  }

  // Overnight: split into two blocks
  const startColStart = Math.min(startHour + 2, 25)
  const spanStart = Math.max(1, 24 - startHour)
  const startColSpan = Math.max(1, Math.min(spanStart, 26 - startColStart))
  const spanEnd = Math.max(1, effectiveEndHour + 1)
  const endColSpan = Math.max(1, Math.min(spanEnd, 26 - 2))
  return [
    {
      shift,
      colStart: startColStart,
      colSpan: startColSpan,
      isOvernight: true,
      part: 'start',
    },
    {
      shift,
      colStart: 2,
      colSpan: endColSpan,
      isOvernight: true,
      part: 'end',
    },
  ]
}

export default function ShiftTimeline({ shifts, date, onShiftClick }: Props) {
  const { t } = useTranslation()
  const [currentHour, setCurrentHour] = useState(new Date().getHours())
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentHour(new Date().getHours())
    }, 60_000)
    return () => clearInterval(interval)
  }, [])

  if (shifts.length === 0) {
    return (
      <EmptyState
        icon={'\u{1F550}'}
        title={t('shifts.noShifts')}
        subtitle={t('shifts.noShiftsDesc')}
      />
    )
  }

  // Group shifts by executor_name
  const executorMap = new Map<string, ShiftBrief[]>()
  for (const shift of shifts) {
    const key = shift.executor_name || (shift.user_id ? `user_${shift.user_id}` : `shift_${shift.id}`)
    if (!executorMap.has(key)) executorMap.set(key, [])
    executorMap.get(key)!.push(shift)
  }

  const hours = Array.from({ length: 24 }, (_, i) => i)
  const isToday =
    date.getFullYear() === new Date().getFullYear() &&
    date.getMonth() === new Date().getMonth() &&
    date.getDate() === new Date().getDate()

  return (
    <div
      ref={scrollRef}
      className="overflow-x-auto overflow-y-visible relative"
    >
      {/* Grid uses dynamic gridTemplateColumns -- must remain inline */}
      <div style={{ display: 'grid', gridTemplateColumns: '180px repeat(24, minmax(44px, 1fr))', minWidth: '1200px' }}>
        {/* Header row */}
        <div className="sticky left-0 z-[3] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-2.5 text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center">
          {t('shifts.executorLabel')}
        </div>
        {hours.map(h => (
          <div
            key={h}
            className={cn(
              'border-b border-border-default py-2.5 text-center text-[11px] font-semibold relative',
              h < 23 && 'border-r border-r-[var(--border-subtle,var(--border))]',
              isToday && h === currentHour
                ? 'text-accent bg-accent-dim'
                : 'text-text-muted'
            )}
          >
            {String(h).padStart(2, '0')}
            {/* Current time indicator */}
            {isToday && h === currentHour && (
              <div className="absolute top-0 bottom-0 left-0 w-0.5 bg-accent opacity-80" />
            )}
          </div>
        ))}

        {/* Executor rows */}
        {Array.from(executorMap.entries()).map(([executorKey, executorShifts]) => {
          const displayName = executorShifts[0].executor_name ?? executorKey
          const blocks: ShiftBlock[] = executorShifts.flatMap(computeBlocks)

          return (
            <div
              key={executorKey}
              className="contents"
            >
              {/* Executor name cell */}
              <div className="sticky left-0 z-[2] bg-bg-card border-b border-border-default border-r border-r-border-default px-3 py-2 flex items-center gap-2 min-h-[52px]">
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-white shrink-0"
                  style={{ background: getGradient(displayName) }}
                >
                  {getInitials(displayName)}
                </div>
                <span className="text-xs font-semibold text-text-primary truncate flex-1">
                  {displayName}
                </span>
              </div>

              {/* 24 hour cells (grid positions 2..25) */}
              {hours.map(h => (
                <div
                  key={h}
                  className={cn(
                    'border-b border-border-default relative min-h-[52px]',
                    h < 23 && 'border-r border-r-[rgba(255,255,255,0.04)]',
                    isToday && h === currentHour && 'bg-accent-dim'
                  )}
                />
              ))}

              {/* Shift blocks overlay row */}
              <div
                className="relative h-0 overflow-visible z-[1]"
                style={{ gridColumn: '1 / -1' }}
              >
                {blocks.map((block, idx) => {
                  const color =
                    SHIFT_TYPE_COLORS[block.shift.shift_type ?? 'regular'] ?? '#3b82f6'
                  const label =
                    block.shift.start_time && block.shift.end_time
                      ? `${formatTime(block.shift.start_time)} — ${formatTime(block.shift.end_time)}`
                      : formatTime(block.shift.start_time)

                  // Dynamic positioning must remain inline
                  return (
                    <div
                      key={`${block.shift.id}-${idx}`}
                      onClick={() => onShiftClick(block.shift)}
                      title={`${displayName} \u00B7 ${label} \u00B7 ${t(`shiftStatus.${block.shift.status}`, block.shift.status)}`}
                      className="absolute cursor-pointer rounded-[6px] px-1.5 py-1 overflow-hidden flex flex-col justify-center gap-px transition-colors duration-150"
                      style={{
                        top: '-52px',
                        left: `calc(180px + (100% - 180px) * ${block.colStart - 2} / 24)`,
                        width: `calc((100% - 180px) * ${block.colSpan} / 24)`,
                        height: '36px',
                        marginTop: '8px',
                        background: `${color}22`,
                        border: `1px solid ${color}66`,
                      }}
                      onMouseEnter={e => {
                        ;(e.currentTarget as HTMLDivElement).style.background =
                          `${color}44`
                      }}
                      onMouseLeave={e => {
                        ;(e.currentTarget as HTMLDivElement).style.background =
                          `${color}22`
                      }}
                    >
                      <span
                        className="text-[10px] font-semibold truncate"
                        style={{ color }}
                      >
                        {label} · {t(`shiftStatus.${block.shift.status}`, block.shift.status)}
                      </span>
                      <span className="text-[10px] text-text-muted font-[var(--font-mono)] whitespace-nowrap">
                        {block.shift.current_request_count}/{block.shift.max_requests}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
