import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent } from '../../utils/timezone'
import { cn } from '@/lib/utils'

interface Props {
  shifts: ShiftBrief[]
  date: Date
}

function isShiftActiveInHour(shift: ShiftBrief, hour: number): boolean {
  const startTZ = toTashkent(shift.start_time)
  const endTZ = shift.end_time ? toTashkent(shift.end_time) : null
  if (!endTZ) return false

  const startH = startTZ.getHours()
  const endH = endTZ.getHours()
  const endM = endTZ.getMinutes()

  // Effective end hour (if shift ends exactly at HH:00, last active hour is HH-1)
  const effectiveEnd = endM > 0 ? endH : Math.max(endH - 1, 0)

  if (startH <= effectiveEnd) {
    // Normal (same-day) shift
    return hour >= startH && hour <= effectiveEnd
  }
  // Overnight shift
  return hour >= startH || hour <= effectiveEnd
}

function getCellColor(count: number): string {
  if (count === 0) return 'rgba(239,68,68,0.3)'
  if (count <= 2) return 'rgba(245,158,11,0.4)'
  if (count <= 4) return 'rgba(var(--accent-rgb),0.35)'
  return 'rgba(var(--accent-rgb),0.65)'
}

const LEGEND = [
  { label: '0', color: 'rgba(239,68,68,0.3)' },
  { label: '1-2', color: 'rgba(245,158,11,0.4)' },
  { label: '3-4', color: 'rgba(var(--accent-rgb),0.35)' },
  { label: '5+', color: 'rgba(var(--accent-rgb),0.65)' },
]

export default function ShiftCoverageHeatmap({ shifts }: Props) {
  const { t } = useTranslation()
  const [hoveredHour, setHoveredHour] = useState<number | null>(null)

  const counts = Array.from({ length: 24 }, (_, h) =>
    shifts.filter(s => isShiftActiveInHour(s, h)).length,
  )

  return (
    <div>
      {/* Heatmap grid */}
      <div className="grid grid-cols-[repeat(24,1fr)] gap-[3px] mb-1.5">
        {counts.map((count, h) => (
          <div
            key={h}
            className={cn(
              'h-10 rounded cursor-default relative transition-opacity duration-150 flex items-center justify-center',
              hoveredHour !== null && hoveredHour !== h && 'opacity-50'
            )}
            style={{ background: getCellColor(count) }}
            onMouseEnter={() => setHoveredHour(h)}
            onMouseLeave={() => setHoveredHour(null)}
          >
            {/* Tooltip */}
            {hoveredHour === h && (
              <div className="absolute bottom-[calc(100%+6px)] left-1/2 -translate-x-1/2 bg-[var(--bg-overlay,#1a1a2e)] border border-border-default rounded-[6px] px-2 py-1 text-[11px] text-text-primary whitespace-nowrap z-10 pointer-events-none">
                {String(h).padStart(2, '0')}:00 {'—'} {count} {t('shifts.executorLabel').toLowerCase()}
              </div>
            )}
            <span
              className="text-[10px] font-[var(--font-mono)] font-semibold"
              style={{
                color: count > 0 ? 'rgba(255,255,255,0.8)' : 'rgba(239,68,68,0.8)',
              }}
            >
              {count}
            </span>
          </div>
        ))}
      </div>

      {/* Hour labels -- only at 00, 06, 12, 18 */}
      <div className="grid grid-cols-[repeat(24,1fr)] gap-[3px] mb-4">
        {Array.from({ length: 24 }, (_, h) => (
          <div
            key={h}
            className="text-center text-[10px] text-text-muted font-[var(--font-mono)]"
          >
            {h % 6 === 0 ? String(h).padStart(2, '0') : ''}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex gap-3 items-center">
        {LEGEND.map(item => (
          <div
            key={item.label}
            className="flex items-center gap-1.5"
          >
            <div
              className="w-3.5 h-3.5 rounded-[3px]"
              style={{ background: item.color }}
            />
            <span className="text-[11px] text-text-muted">
              {item.label}
            </span>
          </div>
        ))}
        <span className="text-[11px] text-text-muted ml-1">
          {t('shifts.executorLabel').toLowerCase()}
        </span>
      </div>
    </div>
  )
}
