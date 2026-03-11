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

export default function KanbanColumn({ column, onCardClick, activeDragStatus }: Props) {
  const frozen = FROZEN_STATUSES.has(column.status)
  const { setNodeRef, isOver } = useDroppable({
    id: column.status,
    disabled: frozen,
  })

  const isValidTarget =
    activeDragStatus !== null &&
    isTransitionAllowed(activeDragStatus, column.status)

  const highlightClass =
    isOver && isValidTarget
      ? 'bg-blue-50 ring-2 ring-blue-400'
      : isOver && !isValidTarget
        ? 'bg-red-50 ring-2 ring-red-300'
        : ''

  return (
    <div className={`flex flex-col min-w-[220px] max-w-[240px] rounded-xl bg-gray-50 p-2 ${highlightClass}`}>
      <div className="flex items-center justify-between mb-2 px-1">
        <span className="font-semibold text-sm">{column.status}</span>
        <span className="bg-gray-200 text-gray-600 text-xs rounded-full px-2 py-0.5">{column.count}</span>
      </div>
      <div ref={setNodeRef} className="flex-1 min-h-[120px]">
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
