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

const STATUS_DOT: Record<string, string> = {
  'Новая':     '#60a5fa',
  'В работе':  '#fbbf24',
  'Закуп':     '#a78bfa',
  'Уточнение': '#22d3ee',
  'Выполнена': '#34d399',
  'Исполнено': '#00d4aa',
  'Принято':   '#4ade80',
  'Отменена':  '#f87171',
}

export default function KanbanColumn({ column, onCardClick, activeDragStatus }: Props) {
  const frozen = FROZEN_STATUSES.has(column.status)
  const { setNodeRef, isOver } = useDroppable({ id: column.status, disabled: frozen })
  const dotColor = STATUS_DOT[column.status] ?? 'var(--text-muted)'

  const isValidTarget = activeDragStatus !== null && isTransitionAllowed(activeDragStatus, column.status)

  let overrideBorder = 'var(--border)'
  if (isOver && isValidTarget)  overrideBorder = 'rgba(59,130,246,0.5)'
  if (isOver && !isValidTarget) overrideBorder = 'rgba(239,68,68,0.5)'

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      minWidth: 240,
      maxWidth: 260,
      background: 'var(--bg-surface)',
      borderRadius: 14,
      border: `1px solid ${overrideBorder}`,
      transition: 'border-color 0.15s',
    }}>
      {/* Column header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        justifyContent: 'space-between',
        padding: '11px 12px 10px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: dotColor, flexShrink: 0,
          }} />
          <span style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: 13,
            color: 'var(--text-primary)',
          }}>{column.status}</span>
        </div>
        <span style={{
          background: 'var(--bg-card)',
          color: 'var(--text-secondary)',
          border: '1px solid var(--border)',
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
