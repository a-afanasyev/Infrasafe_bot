import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DndContext,
  DragOverlay,
  type DragEndEvent,
  type DragStartEvent,
  type DragOverEvent,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { useKanban, type KanbanColumn as TColumn, type RequestCard as TCard } from '../../hooks/useKanban'
import KanbanColumn from './KanbanColumn'
import RequestCard from './RequestCard'
import TransitionModal, { type TransitionData } from './TransitionModal'
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'

// Statuses that require a modal before transitioning
const MODAL_STATUSES = new Set(['В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Исполнено'])

interface PendingTransition {
  requestNumber: string
  newStatus: string
}

interface Props {
  onCardClick: (requestNumber: string) => void
}

const KANBAN_STATUSES = new Set([
  'Новая', 'В работе', 'Закуп', 'Уточнение',
  'Выполнена', 'Исполнено', 'Возвращена', 'Принято', 'Отменена',
])
import { FROZEN_STATUSES } from '../../constants'

// Must mirror backend _REQUEST_VALID_TRANSITIONS exactly
const VALID_TRANSITIONS: Record<string, Set<string>> = {
  'Новая':     new Set(['В работе', 'Закуп', 'Уточнение', 'Отменена']),
  'В работе':  new Set(['Закуп', 'Уточнение', 'Выполнена', 'Отменена']),
  'Закуп':     new Set(['В работе', 'Уточнение', 'Отменена']),
  'Уточнение': new Set(['В работе', 'Отменена']),
  'Выполнена': new Set(['Исполнено', 'В работе']),
  'Исполнено': new Set(['Принято', 'В работе']),
  // PR7: возврат заявителем разбирает менеджер — в работу (доделать),
  // принять (возврат необоснован) или отменить. В «Возвращена» заявка попадает
  // только действием заявителя (APPLICANT_RETURN), не перетаскиванием.
  'Возвращена': new Set(['В работе', 'Принято', 'Отменена']),
  'Принято':   new Set(),
  'Отменена':  new Set(),
}

function resolveTargetStatus(overId: string, columns: TColumn[]): string | null {
  if (KANBAN_STATUSES.has(overId)) return overId
  const col = columns.find(c => c.requests.some(r => r.request_number === overId))
  return col?.status ?? null
}

function isTransitionAllowed(sourceStatus: string | undefined, targetStatus: string): boolean {
  if (!sourceStatus) return false
  if (sourceStatus === targetStatus) return false
  return VALID_TRANSITIONS[sourceStatus]?.has(targetStatus) ?? false
}

/**
 * Назначение исполнителя (canon MANAGER_ASSIGN) применимо ТОЛЬКО при взятии
 * заявки из «Новая» в работу. Из «Закуп»/«Уточнение»/«Выполнена»/«Исполнено»/
 * «Возвращена» «В работе» — это resume/return (MANAGER_PURCHASE_DONE /
 * CLARIFY_RESOLVED / MANAGER_RETURN_TO_WORK), которые executor_id НЕ принимают
 * (иначе backend → 422 «unexpected field 'executor_id'»). Из этих источников
 * переход коммитим напрямую, без модалки выбора исполнителя.
 */
function inProgressNeedsExecutorModal(sourceStatus: string | undefined, hasExecutor: boolean): boolean {
  return sourceStatus === 'Новая' && !hasExecutor
}

export { isTransitionAllowed, FROZEN_STATUSES, VALID_TRANSITIONS, MODAL_STATUSES, inProgressNeedsExecutorModal }

export default function KanbanBoard({ onCardClick }: Props) {
  const { t } = useTranslation()
  const { columns, isLoading, isError } = useKanban()
  const queryClient = useQueryClient()
  const [activeDragStatus, setActiveDragStatus] = useState<string | null>(null)
  const [activeCard, setActiveCard] = useState<TCard | null>(null)
  const [overColumnId, setOverColumnId] = useState<string | null>(null)
  const [overItemId, setOverItemId] = useState<string | null>(null)
  const [pendingTransition, setPendingTransition] = useState<PendingTransition | null>(null)
  const [transitionError, setTransitionError] = useState<string | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 20 } }),
  )

  const handleDragStart = (event: DragStartEvent) => {
    const requestNumber = String(event.active.id)
    const sourceCol = columns.find(col =>
      col.requests.some(r => r.request_number === requestNumber),
    )
    setActiveDragStatus(sourceCol?.status ?? null)
    const card = sourceCol?.requests.find(r => r.request_number === requestNumber) ?? null
    setActiveCard(card)
  }

  const handleDragOver = (event: DragOverEvent) => {
    const { over } = event
    if (!over) {
      setOverColumnId(null)
      setOverItemId(null)
      return
    }
    const overId = String(over.id)
    const targetStatus = resolveTargetStatus(overId, columns)
    setOverColumnId(targetStatus)
    // If hovering over a specific card (not a column droppable), track it
    setOverItemId(KANBAN_STATUSES.has(overId) ? null : overId)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveDragStatus(null)
    setActiveCard(null)
    setOverColumnId(null)
    setOverItemId(null)
    if (!over || active.id === over.id) return

    const requestNumber = String(active.id)
    const newStatus = resolveTargetStatus(String(over.id), columns)
    if (!newStatus) return

    const sourceCol = columns.find(col =>
      col.requests.some(r => r.request_number === requestNumber),
    )
    if (!sourceCol) return
    if (!isTransitionAllowed(sourceCol.status, newStatus)) return

    if (MODAL_STATUSES.has(newStatus)) {
      // 'В работе': модалка выбора исполнителя нужна только при назначении из
      // «Новая» без исполнителя. Из «Закуп»/«Уточнение»/«Выполнена»/«Исполнено»/
      // «Возвращена» это resume/return — коммитим напрямую (executor_id там → 422).
      if (newStatus === 'В работе') {
        const card = columns.flatMap(c => c.requests).find(r => r.request_number === requestNumber)
        if (!inProgressNeedsExecutorModal(sourceCol.status, Boolean(card?.executor_id))) {
          commitTransition(requestNumber, { status: newStatus })
          return
        }
      }
      setPendingTransition({ requestNumber, newStatus })
    } else {
      commitTransition(requestNumber, { status: newStatus })
    }
  }

  const commitTransition = async (requestNumber: string, data: TransitionData) => {
    // Optimistic update
    queryClient.setQueryData(
      ['kanban', {}],
      (old: { columns: typeof columns } | undefined) => {
        if (!old) return old
        const card = old.columns
          .flatMap(c => c.requests)
          .find(r => r.request_number === requestNumber)
        if (!card) return old
        const newStatus = data.status
        return {
          columns: old.columns.map((col) => ({
            ...col,
            requests:
              col.status === newStatus
                ? [...col.requests, { ...card, status: newStatus }]
                : col.requests.filter(r => r.request_number !== requestNumber),
            count:
              col.status === newStatus
                ? col.count + 1
                : col.requests.some(r => r.request_number === requestNumber)
                  ? col.count - 1
                  : col.count,
          })),
        }
      },
    )

    try {
      await apiClient.patch(`/api/v2/requests/${requestNumber}`, data)
    } catch {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
      setTransitionError(t('errors.transitionFailed'))
      setTimeout(() => setTransitionError(null), 4000)
    }
  }

  const handleTransitionConfirm = (data: TransitionData) => {
    if (pendingTransition) {
      commitTransition(pendingTransition.requestNumber, data)
      setPendingTransition(null)
    }
  }

  if (isLoading) {
    return (
      <div className="p-8 text-center text-text-muted font-[family-name:var(--font-body)]">
        {t('common.loading')}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="p-8 text-center text-red-500 font-[family-name:var(--font-body)]">
        {t('common.error')}
      </div>
    )
  }

  return (
    <>
      {transitionError && (
        <div className="mb-2 px-3.5 py-2.5 bg-red/10 border border-red/25 text-red text-[13px] rounded-sm font-[family-name:var(--font-body)]">
          {transitionError}
        </div>
      )}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-2.5 overflow-x-auto pb-4 h-full items-start">
          {columns.map((col) => (
            <KanbanColumn
              key={col.status}
              column={col}
              onCardClick={onCardClick}
              activeDragStatus={activeDragStatus}
              overColumnId={overColumnId}
              overItemId={overItemId}
            />
          ))}
        </div>

        <DragOverlay dropAnimation={null}>
          {activeCard ? (
            <div className="w-[236px] rotate-[2deg] scale-105 opacity-90">
              <RequestCard card={activeCard} onClick={() => {}} isOverlay />
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {pendingTransition && (
        <TransitionModal
          requestNumber={pendingTransition.requestNumber}
          targetStatus={pendingTransition.newStatus}
          onConfirm={handleTransitionConfirm}
          onCancel={() => setPendingTransition(null)}
        />
      )}
    </>
  )
}
