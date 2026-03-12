import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import RequestCard from './RequestCard'
import type { KanbanColumn as TColumn } from '../../hooks/useKanban'
import { isTransitionAllowed, FROZEN_STATUSES } from './KanbanBoard'

interface Props {
  column: TColumn
  onCardClick: (number: string) => void
  activeDragStatus: string | null
}

const STATUS_ACCENT: Record<string, { color: string; bg: string; border: string }> = {
  'Новая':     { color: '#60a5fa', bg: 'rgba(59,130,246,0.08)',  border: 'rgba(59,130,246,0.3)'  },
  'В работе':  { color: '#fbbf24', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.3)'  },
  'Закуп':     { color: '#a78bfa', bg: 'rgba(139,92,246,0.08)',  border: 'rgba(139,92,246,0.3)'  },
  'Уточнение': { color: '#22d3ee', bg: 'rgba(6,182,212,0.08)',   border: 'rgba(6,182,212,0.3)'   },
  'Выполнена': { color: '#34d399', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.3)'  },
  'Исполнено': { color: '#00d4aa', bg: 'rgba(0,212,170,0.08)',   border: 'rgba(0,212,170,0.3)'   },
  'Принято':   { color: '#4ade80', bg: 'rgba(34,197,94,0.08)',   border: 'rgba(34,197,94,0.3)'   },
  'Отменена':  { color: '#f87171', bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.3)'   },
}

export default function KanbanColumn({ column, onCardClick, activeDragStatus }: Props) {
  const frozen = FROZEN_STATUSES.has(column.status)
  const { setNodeRef, isOver } = useDroppable({ id: column.status, disabled: frozen })
  const accent = STATUS_ACCENT[column.status] ?? { color: 'var(--text-secondary)', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.1)' }

  const isValidTarget = activeDragStatus !== null && isTransitionAllowed(activeDragStatus, column.status)

  // Drag-over overlay color
  let dragBorder = 'transparent'
  let dragBg = 'transparent'
  if (isOver && isValidTarget)  { dragBorder = 'rgba(59,130,246,0.5)'; dragBg = 'rgba(59,130,246,0.05)' }
  if (isOver && !isValidTarget) { dragBorder = 'rgba(239,68,68,0.5)';  dragBg = 'rgba(239,68,68,0.05)'  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      minWidth: 240,
      maxWidth: 260,
      background: `linear-gradient(180deg, ${accent.bg} 0%, rgba(10,15,24,0.6) 60%)`,
      backgroundColor: '#0a0f18',
      borderRadius: 14,
      border: `1px solid ${isOver ? dragBorder : accent.border}`,
      boxShadow: isOver && isValidTarget
        ? '0 0 0 2px rgba(59,130,246,0.3)'
        : isOver && !isValidTarget
          ? '0 0 0 2px rgba(239,68,68,0.3)'
          : 'none',
      transition: 'border-color 0.15s, box-shadow 0.15s',
      backgroundColor: isOver ? (isValidTarget ? `rgba(59,130,246,0.04)` : `rgba(239,68,68,0.04)`) : '#0a0f18',
    }}>
      {/* Column header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 14px 10px',
        borderBottom: `1px solid rgba(255,255,255,0.06)`,
        flexShrink: 0,
      }}>
        <span style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: 13,
          color: accent.color,
          letterSpacing: '0.2px',
        }}>{column.status}</span>
        <span style={{
          background: accent.bg,
          color: accent.color,
          border: `1px solid ${accent.border}`,
          fontSize: 11,
          fontWeight: 700,
          borderRadius: 20,
          padding: '1px 8px',
          fontFamily: 'var(--font-display)',
        }}>{column.count}</span>
      </div>

      {/* Cards area */}
      <div
        ref={setNodeRef}
        style={{
          flex: 1,
          minHeight: 120,
          padding: '8px 8px 4px',
          overflowY: 'auto',
        }}
      >
        <SortableContext
          items={column.requests.map((r) => r.request_number)}
          strategy={verticalListSortingStrategy}
        >
          {column.requests.map((card) => (
            <RequestCard
              key={card.request_number}
              card={card}
              onClick={() => onCardClick(card.request_number)}
            />
          ))}
        </SortableContext>
      </div>
    </div>
  )
}
