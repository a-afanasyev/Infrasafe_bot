import { useEffect, useRef, useState } from 'react'
import type { ShiftBrief } from '../../hooks/useShifts'
import { toTashkent, formatTime } from '../../utils/timezone'
import EmptyState from '../shared/EmptyState'

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
        icon="🕐"
        title="Нет смен"
        subtitle="Создайте смену для этого дня"
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

  const gridStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: '180px repeat(24, minmax(44px, 1fr))',
    minWidth: '1200px',
  }

  return (
    <div
      ref={scrollRef}
      style={{ overflowX: 'auto', overflowY: 'visible', position: 'relative' }}
    >
      <div style={gridStyle}>
        {/* Header row */}
        <div
          style={{
            position: 'sticky',
            left: 0,
            zIndex: 3,
            background: 'var(--bg-card)',
            borderBottom: '1px solid var(--border)',
            borderRight: '1px solid var(--border)',
            padding: '10px 12px',
            fontSize: '11px',
            fontWeight: 700,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          Исполнитель
        </div>
        {hours.map(h => (
          <div
            key={h}
            style={{
              borderBottom: '1px solid var(--border)',
              borderRight: h < 23 ? '1px solid var(--border-subtle, var(--border))' : undefined,
              padding: '10px 0',
              textAlign: 'center',
              fontSize: '11px',
              fontWeight: 600,
              color: isToday && h === currentHour ? 'var(--accent)' : 'var(--text-muted)',
              background:
                isToday && h === currentHour
                  ? 'var(--accent-dim)'
                  : 'transparent',
              position: 'relative',
            }}
          >
            {String(h).padStart(2, '0')}
            {/* Current time indicator */}
            {isToday && h === currentHour && (
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  bottom: 0,
                  left: 0,
                  width: '2px',
                  background: 'var(--accent)',
                  opacity: 0.8,
                }}
              />
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
              style={{ display: 'contents' }}
            >
              {/* Executor name cell */}
              <div
                style={{
                  position: 'sticky',
                  left: 0,
                  zIndex: 2,
                  background: 'var(--bg-card)',
                  borderBottom: '1px solid var(--border)',
                  borderRight: '1px solid var(--border)',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  minHeight: '52px',
                }}
              >
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    background: getGradient(displayName),
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '11px',
                    fontWeight: 700,
                    color: '#fff',
                    flexShrink: 0,
                  }}
                >
                  {getInitials(displayName)}
                </div>
                <span
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    flex: 1,
                  }}
                >
                  {displayName}
                </span>
              </div>

              {/* 24 hour cells (grid positions 2..25) */}
              {hours.map(h => (
                <div
                  key={h}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    borderRight:
                      h < 23
                        ? '1px solid var(--border-subtle, rgba(255,255,255,0.04))'
                        : undefined,
                    position: 'relative',
                    minHeight: '52px',
                    background:
                      isToday && h === currentHour
                        ? 'var(--accent-dim)'
                        : 'transparent',
                  }}
                />
              ))}

              {/* Shift blocks — absolutely position over the row using CSS grid overlay trick */}
              {/* We use a second "overlay" row that spans all 25 columns */}
              <div
                style={{
                  gridColumn: '1 / -1',
                  position: 'relative',
                  height: 0,
                  overflow: 'visible',
                  zIndex: 1,
                }}
              >
                {blocks.map((block, idx) => {
                  const color =
                    SHIFT_TYPE_COLORS[block.shift.shift_type ?? 'regular'] ?? '#3b82f6'
                  const label =
                    block.shift.start_time && block.shift.end_time
                      ? `${formatTime(block.shift.start_time)} — ${formatTime(block.shift.end_time)}`
                      : formatTime(block.shift.start_time)

                  return (
                    <div
                      key={`${block.shift.id}-${idx}`}
                      onClick={() => onShiftClick(block.shift)}
                      title={`${displayName} · ${label} · ${block.shift.status}`}
                      style={{
                        position: 'absolute',
                        top: '-52px',
                        // left offset: 180px name col + (colStart-2)/24 of remaining
                        left: `calc(180px + (100% - 180px) * ${block.colStart - 2} / 24)`,
                        width: `calc((100% - 180px) * ${block.colSpan} / 24)`,
                        height: '36px',
                        marginTop: '8px',
                        background: `${color}22`,
                        border: `1px solid ${color}66`,
                        borderRadius: '6px',
                        cursor: 'pointer',
                        padding: '4px 6px',
                        overflow: 'hidden',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        gap: '1px',
                        transition: 'background 0.15s',
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
                        style={{
                          fontSize: '10px',
                          color,
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {label} · {block.shift.status}
                      </span>
                      <span
                        style={{
                          fontSize: '10px',
                          color: 'var(--text-muted)',
                          fontFamily: 'var(--font-mono)',
                          whiteSpace: 'nowrap',
                        }}
                      >
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
