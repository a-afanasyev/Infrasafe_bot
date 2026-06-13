import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useTranslation } from 'react-i18next'
import RequestCard from './RequestCard'
import type { KanbanColumn as TColumn } from '../../hooks/useKanban'
import { isTransitionAllowed, FROZEN_STATUSES } from './KanbanBoard'
import { tStatus } from '../../i18n/apiMaps'
import { cn } from '@/lib/utils'

interface Props {
  column: TColumn
  onCardClick: (number: string) => void
  activeDragStatus: string | null
  overColumnId: string | null
  overItemId: string | null
}

const STATUS_DOT: Record<string, string> = {
  'Новая':     'bg-[#60a5fa]',
  'В работе':  'bg-[#fbbf24]',
  'Закуп':     'bg-[#a78bfa]',
  'Уточнение': 'bg-[#22d3ee]',
  'Выполнена': 'bg-[#34d399]',
  'Исполнено': 'bg-accent',
  'Возвращена': 'bg-[#fb923c]',
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
  'Возвращена': 'shadow-[inset_0_0_32px_rgba(251,146,60,0.1)]',
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
  'Возвращена': 'border-[#fb923c]/40',
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
  'Возвращена': 'border-[#fb923c]/25',
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
  'Возвращена': 'bg-[#fb923c]/[0.04]',
  'Принято':   'bg-[#4ade80]/[0.04]',
  'Отменена':  'bg-[#f87171]/[0.04]',
}

function DropPlaceholder({ status, visible }: { status: string; visible: boolean }) {
  return (
    <div
      className={cn(
        'rounded-[10px] border-2 border-dashed overflow-hidden transition-all duration-200 ease-out',
        visible
          ? cn(
              'h-[76px] mb-1.5 opacity-100',
              PLACEHOLDER_BORDER[status] ?? 'border-accent/25',
              PLACEHOLDER_BG[status] ?? 'bg-accent/[0.04]',
            )
          : 'h-0 mb-0 opacity-0 border-transparent',
      )}
    />
  )
}

export default function KanbanColumn({ column, onCardClick, activeDragStatus, overColumnId, overItemId }: Props) {
  const { t } = useTranslation()
  const frozen = FROZEN_STATUSES.has(column.status)
  const { setNodeRef } = useDroppable({ id: column.status, disabled: frozen })
  const dotClass = STATUS_DOT[column.status] ?? 'bg-text-muted'

  const isDragging = activeDragStatus !== null
  const isValidTarget = isDragging && isTransitionAllowed(activeDragStatus, column.status)
  const isInvalidTarget = isDragging && !isValidTarget && activeDragStatus !== column.status
  const isHoveredValid = overColumnId === column.status && isValidTarget
  const isSource = activeDragStatus === column.status

  // Find insertion index for the placeholder
  const overCardIndex = overItemId
    ? column.requests.findIndex(r => r.request_number === overItemId)
    : -1
  // If hovering over a card in this column, insert before it; otherwise at end
  const placeholderIndex = isHoveredValid
    ? (overCardIndex >= 0 ? overCardIndex : column.requests.length)
    : -1

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
            {tStatus(column.status, t)}
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
          {column.requests.map((card, index) => (
            <div key={card.request_number}>
              {/* Placeholder before this card */}
              <DropPlaceholder
                status={column.status}
                visible={placeholderIndex === index}
              />
              <RequestCard
                card={card}
                onClick={() => onCardClick(card.request_number)}
              />
            </div>
          ))}
          {/* Placeholder at end (when hovering column itself or after last card) */}
          <DropPlaceholder
            status={column.status}
            visible={placeholderIndex === column.requests.length}
          />
          {/* FE-045: empty-state hint when the column has no cards and nothing
              is being dragged (suppressed mid-drag so the drop zone reads clean). */}
          {column.requests.length === 0 && !activeDragStatus && (
            <div className="flex items-center justify-center py-6 text-[11px] text-text-muted select-none">
              {t('kanban.emptyColumn')}
            </div>
          )}
        </SortableContext>
      </div>
    </div>
  )
}
