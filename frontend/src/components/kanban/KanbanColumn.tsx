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
  overColumnId: string | null
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

const STATUS_GLOW: Record<string, string> = {
  'Новая':     'shadow-[inset_0_0_32px_rgba(96,165,250,0.1)]',
  'В работе':  'shadow-[inset_0_0_32px_rgba(251,191,36,0.1)]',
  'Закуп':     'shadow-[inset_0_0_32px_rgba(167,139,250,0.1)]',
  'Уточнение': 'shadow-[inset_0_0_32px_rgba(34,211,238,0.1)]',
  'Выполнена': 'shadow-[inset_0_0_32px_rgba(52,211,153,0.1)]',
  'Исполнено': 'shadow-[inset_0_0_32px_rgba(0,212,170,0.1)]',
  'Принято':   'shadow-[inset_0_0_32px_rgba(74,222,128,0.1)]',
  'Отменена':  'shadow-[inset_0_0_32px_rgba(248,113,113,0.1)]',
}

const STATUS_BORDER_ACTIVE: Record<string, string> = {
  'Новая':     'border-[#60a5fa]/40',
  'В работе':  'border-[#fbbf24]/40',
  'Закуп':     'border-[#a78bfa]/40',
  'Уточнение': 'border-[#22d3ee]/40',
  'Выполнена': 'border-[#34d399]/40',
  'Исполнено': 'border-accent/40',
  'Принято':   'border-[#4ade80]/40',
  'Отменена':  'border-[#f87171]/40',
}

const PLACEHOLDER_BORDER: Record<string, string> = {
  'Новая':     'border-[#60a5fa]/25',
  'В работе':  'border-[#fbbf24]/25',
  'Закуп':     'border-[#a78bfa]/25',
  'Уточнение': 'border-[#22d3ee]/25',
  'Выполнена': 'border-[#34d399]/25',
  'Исполнено': 'border-accent/25',
  'Принято':   'border-[#4ade80]/25',
  'Отменена':  'border-[#f87171]/25',
}

const PLACEHOLDER_BG: Record<string, string> = {
  'Новая':     'bg-[#60a5fa]/[0.04]',
  'В работе':  'bg-[#fbbf24]/[0.04]',
  'Закуп':     'bg-[#a78bfa]/[0.04]',
  'Уточнение': 'bg-[#22d3ee]/[0.04]',
  'Выполнена': 'bg-[#34d399]/[0.04]',
  'Исполнено': 'bg-accent/[0.04]',
  'Принято':   'bg-[#4ade80]/[0.04]',
  'Отменена':  'bg-[#f87171]/[0.04]',
}

export default function KanbanColumn({ column, onCardClick, activeDragStatus, overColumnId }: Props) {
  const frozen = FROZEN_STATUSES.has(column.status)
  const { setNodeRef } = useDroppable({ id: column.status, disabled: frozen })
  const dotClass = STATUS_DOT[column.status] ?? 'bg-text-muted'

  const isDragging = activeDragStatus !== null
  const isValidTarget = isDragging && isTransitionAllowed(activeDragStatus, column.status)
  const isInvalidTarget = isDragging && !isValidTarget && activeDragStatus !== column.status
  const isHoveredValid = overColumnId === column.status && isValidTarget
  const isSource = activeDragStatus === column.status

  return (
    <div className={cn(
      'flex flex-col min-w-[240px] max-w-[260px] rounded-[14px] border transition-all duration-200',
      isHoveredValid
        ? cn(
            STATUS_BORDER_ACTIVE[column.status] ?? 'border-accent/40',
            STATUS_GLOW[column.status] ?? '',
            'bg-bg-surface scale-[1.01]',
          )
        : isValidTarget
          ? 'border-border-default bg-bg-surface'
          : isInvalidTarget
            ? 'border-border-default bg-bg-surface opacity-50'
            : isSource
              ? 'border-border-default bg-bg-surface opacity-70'
              : 'border-border-default bg-bg-surface',
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
        className={cn(
          'flex-1 min-h-[120px] p-2 pb-1 overflow-y-auto transition-all duration-200',
          isHoveredValid && 'pt-0',
        )}
      >
        {/* Drop placeholder — pushes cards down */}
        <div
          className={cn(
            'rounded-[10px] border-2 border-dashed overflow-hidden transition-all duration-200 ease-out',
            isHoveredValid
              ? cn(
                  'h-[76px] mb-1.5 opacity-100',
                  PLACEHOLDER_BORDER[column.status] ?? 'border-accent/25',
                  PLACEHOLDER_BG[column.status] ?? 'bg-accent/[0.04]',
                )
              : 'h-0 mb-0 opacity-0 border-transparent',
          )}
        />

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
