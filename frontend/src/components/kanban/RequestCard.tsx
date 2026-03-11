import { useRef } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { RequestCard as TCard } from '../../hooks/useKanban'

const URGENCY_COLOR: Record<string, string> = {
  'Обычная': 'bg-green-100 text-green-700',
  'Средняя': 'bg-yellow-100 text-yellow-700',
  'Срочная': 'bg-orange-100 text-orange-700',
  'Критическая': 'bg-red-100 text-red-700',
}

const SOURCE_ICON: Record<string, string> = {
  bot: '\u{1F916}',
  twa: '\u{1F4F1}',
  web: '\u{1F310}',
  call_center: '\u{1F4DE}',
}

const FROZEN_STATUSES = new Set(['Принято', 'Отменена'])

interface Props {
  card: TCard
  onClick: () => void
}

export default function RequestCard({ card, onClick }: Props) {
  const urgencyClass = URGENCY_COLOR[card.urgency ?? ''] ?? 'bg-gray-100 text-gray-600'
  const pointerStart = useRef<{ x: number; y: number } | null>(null)
  const frozen = FROZEN_STATUSES.has(card.status)

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: card.request_number,
    disabled: frozen ? { draggable: true, droppable: true } : false,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
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
          if (Math.abs(dx) < 5 && Math.abs(dy) < 5) {
            onClick()
          }
          pointerStart.current = null
        }
      }}
      className={`bg-white border rounded-xl p-3 transition-shadow mb-2 ${frozen ? 'opacity-70' : 'cursor-pointer hover:shadow-md'}`}
    >
      <div className="flex justify-between items-start mb-1">
        <span className="font-mono text-xs text-gray-500">{card.request_number}</span>
        <span className="text-xs">{SOURCE_ICON[card.source ?? ''] ?? ''}</span>
      </div>
      <p className="text-sm font-medium mb-1">{card.category}</p>
      <p className="text-xs text-gray-500 line-clamp-2">{card.description}</p>
      <div className="mt-2 flex gap-1 flex-wrap">
        {card.urgency && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${urgencyClass}`}>{card.urgency}</span>
        )}
        {card.manager_confirmed && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">{'\u2713'} Подтверждено</span>
        )}
      </div>
    </div>
  )
}
