import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { useWebSocket } from './useWebSocket'

export interface RequestCard {
  request_number: string
  status: string
  category: string
  urgency: string | null
  source: string | null
  description: string | null
  address: string | null
  executor_id: number | null
  executor_name: string | null
  notes: string | null
  completion_report: string | null
  requested_materials: string | null
  return_reason: string | null
  created_at: string
  updated_at: string | null
  manager_confirmed: boolean
}

export interface KanbanColumn {
  status: string
  count: number
  requests: RequestCard[]
}

/** Префикс кэша канбана. Инвалидация по нему накрывает все варианты фильтров. */
export const KANBAN_QUERY_PREFIX = ['kanban'] as const

/** Единственный способ собрать ключ кэша канбана.
 *
 * AUD5-APIFE-8: `KanbanBoard` писал оптимистичное обновление в захардкоженный
 * `['kanban', {}]`, который совпадает с реальным ключом только пока фильтров
 * нет. Фабрика + возврат `queryKey` из хука убирают возможность такого
 * расхождения в принципе — писать и читать больше нечем.
 */
export function kanbanQueryKey(filters: Record<string, string | undefined> = {}) {
  return [...KANBAN_QUERY_PREFIX, filters] as const
}

export function useKanban(filters: Record<string, string | undefined> = {}) {
  const queryClient = useQueryClient()
  const queryKey = kanbanQueryKey(filters)

  const { data, isLoading, isError } = useQuery<{ columns: KanbanColumn[] }>({
    queryKey,
    queryFn: () => apiClient.get('/api/v2/requests/kanban', { params: filters }).then((r) => r.data),
    staleTime: 30_000,
    // Страховка к WS: доска обязана показать ответ жителя на уточнение даже
    // если сокет мёртв (AUD5-APIFE-7). Минута — компромисс между свежестью
    // индикаторов и нагрузкой.
    refetchInterval: 60_000,
  })

  useWebSocket('kanban', (event) => {
    if (['request.created', 'request.status_changed', 'request.assigned', 'request.updated'].includes(event.type)) {
      queryClient.invalidateQueries({ queryKey: KANBAN_QUERY_PREFIX })
    }
  })

  return { columns: data?.columns ?? [], isLoading, isError, queryKey }
}
