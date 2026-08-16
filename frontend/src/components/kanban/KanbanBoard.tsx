import { useMemo, useState } from 'react'
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
import { useKanban, type RequestCard as TCard } from '../../hooks/useKanban'
import KanbanColumn from './KanbanColumn'
import RequestCard from './RequestCard'
import TransitionModal, { type TransitionData } from './TransitionModal'
import { commitTransition as doCommitTransition } from './commitTransition'
import { useQueryClient } from '@tanstack/react-query'
import { useSeenRequests } from '../../hooks/useSeenRequests'
import {
  MODAL_STATUSES,
  KANBAN_STATUSES,
  resolveTargetStatus,
  isTransitionAllowed,
  inProgressNeedsExecutorModal,
} from './transitions'

// Колонки, где отслеживается «непрочитанное». Остальные не подсвечиваем:
// «В работе» меняется постоянно и точка там означала бы только шум.
const UNREAD_TRACKED_STATUSES = new Set(['Уточнение', 'Закуп'])

interface PendingTransition {
  requestNumber: string
  newStatus: string
}

interface Props {
  onCardClick: (requestNumber: string) => void
}

export default function KanbanBoard({ onCardClick }: Props) {
  const { t } = useTranslation()
  const { columns, isLoading, isError, queryKey } = useKanban()
  const queryClient = useQueryClient()
  const [activeDragStatus, setActiveDragStatus] = useState<string | null>(null)
  const [activeCard, setActiveCard] = useState<TCard | null>(null)
  const [overColumnId, setOverColumnId] = useState<string | null>(null)
  const [overItemId, setOverItemId] = useState<string | null>(null)
  const [pendingTransition, setPendingTransition] = useState<PendingTransition | null>(null)
  const [transitionError, setTransitionError] = useState<string | null>(null)
  const { isUnread, markSeen } = useSeenRequests()

  // Индикаторы считаем один раз на доску: вниз идёт множество номеров, колонки
  // и карточки остаются презентационными. Отслеживаем только те колонки, где
  // менеджеру важно увидеть обновление: ответ жителя на уточнение и новая
  // заявка на закуп.
  const unreadNumbers = useMemo(() => {
    const result = new Set<string>()
    for (const col of columns) {
      if (!UNREAD_TRACKED_STATUSES.has(col.status)) continue
      for (const card of col.requests) {
        if (isUnread(card.request_number, card.updated_at, card.created_at)) {
          result.add(card.request_number)
        }
      }
    }
    return result
  }, [columns, isUnread])

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

  const commitTransition = (requestNumber: string, data: TransitionData) =>
    // Тело вынесено в модуль (AUD5-APIFE-8): внутри компонента оно достигалось
    // только симуляцией drag&drop и потому оставалось непокрытым.
    doCommitTransition({
      queryClient,
      queryKey,
      requestNumber,
      data,
      onError: () => {
        setTransitionError(t('errors.transitionFailed'))
        setTimeout(() => setTransitionError(null), 4000)
      },
      // `updated_at` бампает onupdate на самой колонке, поэтому собственный
      // drag менеджера в «Уточнение»/«Закуп» иначе сразу зажёг бы точку на
      // карточке, которую он только что туда перетащил.
      onSuccess: (card) => markSeen(requestNumber, card?.updated_at ?? null),
    })

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
        {/* Внешний div скроллит всю доску; внутренний min-h-full + items-stretch тянут
            все колонки до высоты самой длинной, чтобы sticky-заголовки (top-0) держались
            даже у пустых/коротких колонок до самого низа прокрутки. */}
        <div className="kanban-hscroll min-h-0 flex-1 overflow-auto pb-2.5">
          <div className="flex min-h-full items-stretch gap-2.5">
            {columns.map((col) => (
              <KanbanColumn
                key={col.status}
                column={col}
                onCardClick={onCardClick}
                activeDragStatus={activeDragStatus}
                overColumnId={overColumnId}
                overItemId={overItemId}
                unreadNumbers={unreadNumbers}
              />
            ))}
          </div>
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
