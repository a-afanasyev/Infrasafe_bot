import { useState } from 'react'
import {
  DndContext,
  type DragEndEvent,
  type DragStartEvent,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { useKanban, type KanbanColumn as TColumn } from '../../hooks/useKanban'
import KanbanColumn from './KanbanColumn'
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
  'Выполнена', 'Исполнено', 'Принято', 'Отменена',
])
const FROZEN_STATUSES = new Set(['Принято', 'Отменена'])

function resolveTargetStatus(overId: string, columns: TColumn[]): string | null {
  if (KANBAN_STATUSES.has(overId)) return overId
  const col = columns.find(c => c.requests.some(r => r.request_number === overId))
  return col?.status ?? null
}

function isTransitionAllowed(sourceStatus: string | undefined, targetStatus: string): boolean {
  if (!sourceStatus) return false
  if (sourceStatus === targetStatus) return false
  if (FROZEN_STATUSES.has(sourceStatus)) return false
  if (FROZEN_STATUSES.has(targetStatus)) return false
  if (targetStatus === 'Новая' && sourceStatus !== 'Новая') return false
  // Enforce lifecycle: Выполнена can only go to Исполнено, Исполнено can only go to Принято
  if (sourceStatus === 'Выполнена' && targetStatus !== 'Исполнено') return false
  if (sourceStatus === 'Исполнено' && targetStatus !== 'Принято') return false
  return true
}

export { isTransitionAllowed, FROZEN_STATUSES }

export default function KanbanBoard({ onCardClick }: Props) {
  const { columns, isLoading } = useKanban()
  const queryClient = useQueryClient()
  const [activeDragStatus, setActiveDragStatus] = useState<string | null>(null)
  const [pendingTransition, setPendingTransition] = useState<PendingTransition | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  )

  const handleDragStart = (event: DragStartEvent) => {
    const requestNumber = String(event.active.id)
    const sourceCol = columns.find(col =>
      col.requests.some(r => r.request_number === requestNumber),
    )
    setActiveDragStatus(sourceCol?.status ?? null)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveDragStatus(null)
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
      <div className="p-8 text-center text-gray-400">Загрузка...</div>
    )
  }

  return (
    <>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex gap-3 overflow-x-auto pb-4 h-full">
          {columns.map((col) => (
            <KanbanColumn
              key={col.status}
              column={col}
              onCardClick={onCardClick}
              activeDragStatus={activeDragStatus}
            />
          ))}
        </div>
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
