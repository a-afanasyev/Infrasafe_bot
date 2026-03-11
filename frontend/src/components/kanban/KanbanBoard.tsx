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
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'

interface Props {
  onCardClick: (requestNumber: string) => void
}

const KANBAN_STATUSES = new Set([
  'Новая', 'В работе', 'Закуп', 'Уточнение',
  'Выполнена', 'Исполнено', 'Принято', 'Отменена',
])
const FROZEN_STATUSES = new Set(['Принято', 'Отменена'])

/** Resolve over.id to a column status (handles both column drops and card drops). */
function resolveTargetStatus(
  overId: string,
  columns: TColumn[],
): string | null {
  if (KANBAN_STATUSES.has(overId)) return overId
  const col = columns.find(c => c.requests.some(r => r.request_number === overId))
  return col?.status ?? null
}

/** Check whether moving from sourceStatus -> targetStatus is allowed. */
function isTransitionAllowed(
  sourceStatus: string | undefined,
  targetStatus: string,
): boolean {
  if (!sourceStatus) return false
  if (sourceStatus === targetStatus) return false
  if (FROZEN_STATUSES.has(sourceStatus)) return false
  if (FROZEN_STATUSES.has(targetStatus)) return false
  if (targetStatus === 'Новая' && sourceStatus !== 'Новая') return false
  return true
}

export { isTransitionAllowed, FROZEN_STATUSES }

export default function KanbanBoard({ onCardClick }: Props) {
  const { columns, isLoading } = useKanban()
  const queryClient = useQueryClient()
  const [activeDragStatus, setActiveDragStatus] = useState<string | null>(null)

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

  const handleDragEnd = async (event: DragEndEvent) => {
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

    // Guard: enforce all transition rules — card snaps back if invalid
    if (!isTransitionAllowed(sourceCol.status, newStatus)) return

    // Optimistic update
    queryClient.setQueryData(
      ['kanban', {}],
      (old: { columns: typeof columns } | undefined) => {
        if (!old) return old
        const card = old.columns
          .flatMap(c => c.requests)
          .find(r => r.request_number === requestNumber)
        if (!card) return old
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
                : col.status === sourceCol.status
                  ? col.count - 1
                  : col.count,
          })),
        }
      },
    )

    try {
      await apiClient.patch(`/api/v2/requests/${requestNumber}`, {
        status: newStatus,
      })
    } catch {
      queryClient.invalidateQueries({ queryKey: ['kanban'] })
    }
  }

  if (isLoading) {
    return (
      <div className="p-8 text-center text-gray-400">Загрузка...</div>
    )
  }

  return (
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
  )
}
