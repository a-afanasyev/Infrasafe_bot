import { useRef } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { RequestCard as TCard } from '../../hooks/useKanban'
import { cn } from '@/lib/utils'

const URGENCY: Record<string, { bg: string; text: string }> = {
  'Обычная':    { bg: 'bg-emerald/12',   text: 'text-emerald' },
  'Средняя':    { bg: 'bg-amber/12',     text: 'text-[#d97706]' },
  'Срочная':    { bg: 'bg-[#ea580c]/12', text: 'text-[#ea580c]' },
  'Критическая':{ bg: 'bg-red/12',       text: 'text-red' },
}

const SOURCE_ICON: Record<string, string> = {
  bot: '🤖', twa: '📱', web: '🌐', call_center: '📞',
}

const FROZEN_STATUSES = new Set(['Принято', 'Отменена'])

interface Props {
  card: TCard
  onClick: () => void
  isOverlay?: boolean
}

export default function RequestCard({ card, onClick, isOverlay }: Props) {
  const urgency = URGENCY[card.urgency ?? '']
  const pointerStart = useRef<{ x: number; y: number } | null>(null)
  const frozen = FROZEN_STATUSES.has(card.status)

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: card.request_number,
    disabled: frozen ? { draggable: true, droppable: true } : false,
  })

  // Overlay card (floating under cursor)
  if (isOverlay) {
    return (
      <div className="bg-bg-card border border-accent/30 rounded-[10px] px-3 py-2.5 shadow-[0_12px_40px_rgba(0,0,0,0.3),0_0_0_1px_rgba(0,212,170,0.15)]">
        <CardContent card={card} urgency={urgency} />
      </div>
    )
  }

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      className={cn(
        'bg-bg-card border border-border-default rounded-[10px] px-3 py-2.5 mb-1.5 select-none',
        isDragging && 'opacity-0 h-0 !mb-0 !py-0 !px-0 overflow-hidden border-0',
        frozen ? 'opacity-65 cursor-default' : 'cursor-pointer',
      )}
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
      <CardContent card={card} urgency={urgency} />
    </div>
  )
}

function CardContent({ card, urgency }: { card: TCard; urgency: { bg: string; text: string } | undefined }) {
  return (
    <>
      {/* Header row */}
      <div className="flex justify-between items-center mb-[5px]">
        <span className="font-[family-name:var(--font-mono)] text-[10px] text-text-muted tracking-wide">
          {card.request_number}
        </span>
        <span className="text-[11px] opacity-80">
          {SOURCE_ICON[card.source ?? ''] ?? ''}
        </span>
      </div>

      {/* Category */}
      <div className="font-[family-name:var(--font-display)] font-bold text-[13px] text-text-primary mb-[3px]">
        {card.category}
      </div>

      {/* Description */}
      <div className={cn(
        'text-xs text-text-secondary leading-[1.45] line-clamp-2',
        card.executor_name ? 'mb-[5px]' : 'mb-0'
      )}>
        {card.description}
      </div>

      {/* Executor */}
      {card.executor_name && (
        <div className="text-[11px] text-text-muted mb-[5px] flex items-center gap-1">
          <span>👤</span>
          <span className="overflow-hidden text-ellipsis whitespace-nowrap">
            {card.executor_name}
          </span>
        </div>
      )}

      {/* Badges */}
      {(card.urgency || card.manager_confirmed) && (
        <div className="flex gap-1 flex-wrap mt-1">
          {urgency && (
            <span className={cn(
              'text-[10px] font-bold px-2 py-0.5 rounded-full font-[family-name:var(--font-display)]',
              urgency.bg, urgency.text
            )}>
              {card.urgency}
            </span>
          )}
          {card.manager_confirmed && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue/12 text-blue font-[family-name:var(--font-display)]">
              ✓ Подтверждено
            </span>
          )}
        </div>
      )}
    </>
  )
}
