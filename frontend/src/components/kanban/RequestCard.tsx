import { useRef } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { RequestCard as TCard } from '../../hooks/useKanban'

const URGENCY: Record<string, { bg: string; color: string }> = {
  'Обычная':    { bg: 'rgba(16,185,129,0.12)',  color: '#10b981' },
  'Средняя':    { bg: 'rgba(245,158,11,0.12)',  color: '#f59e0b' },
  'Срочная':    { bg: 'rgba(249,115,22,0.12)',  color: '#f97316' },
  'Критическая':{ bg: 'rgba(239,68,68,0.12)',   color: '#ef4444' },
}

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞',
}

const FROZEN_STATUSES = new Set(['Принято', 'Отменена'])

interface Props {
  card: TCard
  onClick: () => void
}

export default function RequestCard({ card, onClick }: Props) {
  const urgency = URGENCY[card.urgency ?? '']
  const pointerStart = useRef<{ x: number; y: number } | null>(null)
  const frozen = FROZEN_STATUSES.has(card.status)

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: card.request_number,
    disabled: frozen ? { draggable: true, droppable: true } : false,
  })

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.4 : frozen ? 0.65 : 1,
        background: 'var(--bg-card)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 10,
        padding: '10px 12px',
        marginBottom: 6,
        cursor: frozen ? 'default' : 'pointer',
        userSelect: 'none',
        boxShadow: isDragging ? '0 8px 32px rgba(0,0,0,0.4)' : 'none',
      }}
      {...attributes}
      {...listeners}
      onPointerDown={(e) => {
        pointerStart.current = { x: e.clientX, y: e.clientY }
        listeners?.onPointerDown?.(e as never)
      }}
      onPointerUp={(e) => {
        if (pointerStart.current) {
          const dx = e.clientX - pointerStart.current.x
          const dy = e.clientY - pointerStart.current.y
          if (Math.abs(dx) < 5 && Math.abs(dy) < 5) onClick()
          pointerStart.current = null
        }
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text-muted)',
          letterSpacing: '0.3px',
        }}>{card.request_number}</span>
        <span style={{ fontSize: 12, opacity: 0.7 }}>
          {SOURCE_ICON[card.source ?? ''] ?? ''}
        </span>
      </div>

      {/* Category */}
      <div style={{
        fontSize: 11,
        fontWeight: 600,
        color: 'var(--accent)',
        fontFamily: 'var(--font-display)',
        marginBottom: 4,
        letterSpacing: '0.2px',
      }}>{card.category}</div>

      {/* Description */}
      <div style={{
        fontSize: 12,
        color: 'var(--text-primary)',
        lineHeight: 1.45,
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
        marginBottom: card.executor_name ? 6 : 0,
      }}>{card.description}</div>

      {/* Executor */}
      {card.executor_name && (
        <div style={{
          fontSize: 11,
          color: 'var(--text-secondary)',
          marginBottom: 6,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}>
          <span style={{ opacity: 0.6 }}>👤</span>
          <span style={{
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>{card.executor_name}</span>
        </div>
      )}

      {/* Badges */}
      {(card.urgency || card.manager_confirmed) && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
          {urgency && (
            <span style={{
              fontSize: 10,
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: 20,
              background: urgency.bg,
              color: urgency.color,
              fontFamily: 'var(--font-display)',
              letterSpacing: '0.2px',
            }}>{card.urgency}</span>
          )}
          {card.manager_confirmed && (
            <span style={{
              fontSize: 10,
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: 20,
              background: 'rgba(59,130,246,0.12)',
              color: '#60a5fa',
              fontFamily: 'var(--font-display)',
            }}>✓ Подтверждено</span>
          )}
        </div>
      )}
    </div>
  )
}
