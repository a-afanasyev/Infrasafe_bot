import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import RequestCard from './RequestCard'
import type { KanbanColumn as TColumn } from '../../hooks/useKanban'
import { isTransitionAllowed, FROZEN_STATUSES } from './KanbanBoard'
import { cn } from '@/lib/utils'

interface Props {
  column: TColumn
  onCardClick: (number: string) => void
  activeDragStatus: string | null
}

const STATUS_DOT: Record<string, string> = {
  'Новая':     'bg-[#60a5fa]',
  'В работе':  'bg-[#fbbf24]',
  'Закуп':     'bg-[#a78bfa]',
  'Уточнение': 'bg-[#22d3ee]',
  'Выполнена': 'bg-[#34d399]',
  'Исполнено': 'bg-accent',
  'Принято':   'bg-[#4ade80]',
  'Отменена':  'bg-[#f87171]',
}

export default function KanbanColumn({ column, onCardClick, activeDragStatus }: Props) {
  const frozen = FROZEN_STATUSES.has(column.status)
  const { setNodeRef, isOver } = useDroppable({ id: column.status, disabled: frozen })
  const dotClass = STATUS_DOT[column.status] ?? 'bg-text-muted'

  const isValidTarget = activeDragStatus !== null && isTransitionAllowed(activeDragStatus, column.status)

  return (
    <div className={cn(
      'flex flex-col min-w-[240px] max-w-[260px] bg-bg-surface rounded-[14px] border transition-colors duration-150',
      isOver && isValidTarget
        ? 'border-blue/50'
        : isOver && !isValidTarget
        ? 'border-red/50'
        : 'border-border-default'
    )}>
      {/* Column header */}
      <div className="flex items-center gap-[7px] justify-between px-3 pt-[11px] pb-2.5 border-b border-border-default shrink-0">
        <div className="flex items-center gap-[7px]">
          <span className={cn('w-[7px] h-[7px] rounded-full shrink-0', dotClass)} />
          <span className="font-[family-name:var(--font-display)] font-bold text-[13px] text-text-primary">
            {column.status}
          </span>
        </div>
        <span className="bg-bg-card text-text-secondary border border-border-default text-[11px] font-bold rounded-full px-2 py-px font-[family-name:var(--font-display)]">
          {column.count}
        </span>
      </div>

      {/* Cards area */}
      <div
        ref={setNodeRef}
        className="flex-1 min-h-[120px] p-2 pb-1 overflow-y-auto"
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
