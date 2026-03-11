import { useState } from 'react'
import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent } from '../../utils/timezone'

interface Props {
  shifts: ShiftBrief[]
  date: Date
}

function isShiftActiveInHour(shift: ShiftBrief, hour: number): boolean {
  const start = toTashkent(shift.start_time)
  const end = shift.end_time ? toTashkent(shift.end_time) : null
  if (!end) return false
  const slotStart = new Date(
    start.getFullYear(),
    start.getMonth(),
    start.getDate(),
    hour,
    0,
    0,
  )
  const slotEnd = new Date(
    start.getFullYear(),
    start.getMonth(),
    start.getDate(),
    hour,
    59,
    59,
  )
  return start <= slotEnd && end >= slotStart
}

function getCellColor(count: number): string {
  if (count === 0) return 'rgba(239,68,68,0.3)'
  if (count <= 2) return 'rgba(245,158,11,0.4)'
  if (count <= 4) return 'rgba(0,212,170,0.35)'
  return 'rgba(0,212,170,0.65)'
}

const LEGEND = [
  { label: '0', color: 'rgba(239,68,68,0.3)' },
  { label: '1–2', color: 'rgba(245,158,11,0.4)' },
  { label: '3–4', color: 'rgba(0,212,170,0.35)' },
  { label: '5+', color: 'rgba(0,212,170,0.65)' },
]

export default function ShiftCoverageHeatmap({ shifts }: Props) {
  const [hoveredHour, setHoveredHour] = useState<number | null>(null)

  const counts = Array.from({ length: 24 }, (_, h) =>
    shifts.filter(s => isShiftActiveInHour(s, h)).length,
  )

  return (
    <div>
      {/* Heatmap grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(24, 1fr)',
          gap: '3px',
          marginBottom: '6px',
        }}
      >
        {counts.map((count, h) => (
          <div
            key={h}
            style={{
              height: '40px',
              background: getCellColor(count),
              borderRadius: '4px',
              cursor: 'default',
              position: 'relative',
              transition: 'opacity 0.15s',
              opacity: hoveredHour === null || hoveredHour === h ? 1 : 0.5,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onMouseEnter={() => setHoveredHour(h)}
            onMouseLeave={() => setHoveredHour(null)}
          >
            {/* Tooltip */}
            {hoveredHour === h && (
              <div
                style={{
                  position: 'absolute',
                  bottom: 'calc(100% + 6px)',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  background: 'var(--bg-overlay, #1a1a2e)',
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  padding: '4px 8px',
                  fontSize: '11px',
                  color: 'var(--text-primary)',
                  whiteSpace: 'nowrap',
                  zIndex: 10,
                  pointerEvents: 'none',
                }}
              >
                {String(h).padStart(2, '0')}:00 — {count} исп.
              </div>
            )}
            <span
              style={{
                fontSize: '10px',
                fontFamily: 'var(--font-mono)',
                color: count > 0 ? 'rgba(255,255,255,0.8)' : 'rgba(239,68,68,0.8)',
                fontWeight: 600,
              }}
            >
              {count}
            </span>
          </div>
        ))}
      </div>

      {/* Hour labels — only at 00, 06, 12, 18 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(24, 1fr)',
          gap: '3px',
          marginBottom: '16px',
        }}
      >
        {Array.from({ length: 24 }, (_, h) => (
          <div
            key={h}
            style={{
              textAlign: 'center',
              fontSize: '10px',
              color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            {h % 6 === 0 ? String(h).padStart(2, '0') : ''}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
        {LEGEND.map(item => (
          <div
            key={item.label}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <div
              style={{
                width: 14,
                height: 14,
                background: item.color,
                borderRadius: '3px',
              }}
            />
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {item.label}
            </span>
          </div>
        ))}
        <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>
          исполнителей
        </span>
      </div>
    </div>
  )
}
