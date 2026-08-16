import type { QueryClient } from '@tanstack/react-query'

import { apiClient } from '../../api/client'
import { KANBAN_QUERY_PREFIX, type KanbanColumn, type RequestCard } from '../../hooks/useKanban'
import type { TransitionData } from './TransitionModal'

/** Снимок доски в кэше — ровно то, что кладёт туда `useKanban`. */
export interface KanbanBoardData {
  columns: KanbanColumn[]
}

/** Перенести карточку в целевую колонку локально, до ответа сервера.
 *
 * Вынесено из `KanbanBoard.tsx` (AUD5-APIFE-8): внутри компонента этот код
 * достигался только симуляцией drag&drop, поэтому обе его ошибки — чужой ключ
 * кэша и отсутствие реконсиляции при успехе — тестами не покрывались.
 *
 * Возвращает исходный объект без изменений, если заявки на доске нет: писать
 * в кэш «ничего» безопаснее, чем угадывать.
 */
export function applyOptimisticTransition(
  old: KanbanBoardData | undefined,
  requestNumber: string,
  newStatus: string,
): KanbanBoardData | undefined {
  if (!old) return old
  const card = old.columns
    .flatMap((c: KanbanColumn) => c.requests)
    .find((r: RequestCard) => r.request_number === requestNumber)
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
          : col.requests.some(r => r.request_number === requestNumber)
            ? col.count - 1
            : col.count,
    })),
  }
}

interface CommitTransitionArgs {
  queryClient: QueryClient
  /** Ключ, который РЕАЛЬНО читает `useKanban` — берётся из хука, не собирается заново. */
  queryKey: readonly unknown[]
  requestNumber: string
  data: TransitionData
  onError: () => void
  /** Карточка из ответа PATCH. Нужна вызывающему, чтобы отметить заявку
   *  прочитанной на той версии, которую он сам же и создал переходом —
   *  `updated_at` бампается любым изменением строки, включая своё. */
  onSuccess?: (card: RequestCard | undefined) => void
}

/** Применить переход: оптимистично локально, затем PATCH, затем сверка с сервером.
 *
 * Инвалидация в `finally`, а не только в `catch` (AUD5-APIFE-8): успешный PATCH
 * тоже меняет состояние на сервере (номера, автоназначения, производные поля), и
 * полагаться на WS как на единственный путь реконсиляции нельзя — он может быть
 * мёртв, что и есть отдельный пункт AUD5-APIFE-7.
 *
 * Инвалидация идёт по ПРЕФИКСУ `['kanban']`, а не по точному ключу: варианты с
 * разными фильтрами показывают ту же заявку и обязаны обновиться тоже.
 */
export async function commitTransition({
  queryClient,
  queryKey,
  requestNumber,
  data,
  onError,
  onSuccess,
}: CommitTransitionArgs): Promise<void> {
  queryClient.setQueryData(queryKey, (old: KanbanBoardData | undefined) =>
    applyOptimisticTransition(old, requestNumber, data.status),
  )

  try {
    const response = await apiClient.patch(`/api/v2/requests/${requestNumber}`, data)
    onSuccess?.(response?.data as RequestCard | undefined)
  } catch {
    onError()
  } finally {
    queryClient.invalidateQueries({ queryKey: KANBAN_QUERY_PREFIX })
  }
}
