import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import type { TwaRequest } from '../types'
import { twaClient } from '../twaClient'

// «Возвращена» — первой: житель вернул работу, решает менеджер, исполнитель
// должен это заметить. Порядок = порядок групп на странице «Задания».
export const EXECUTOR_ACTIVE_STATUSES = ['Возвращена', 'В работе', 'Закуп', 'Уточнение', 'Новая']
export const EXECUTOR_ARCHIVE_STATUSES = ['Выполнена', 'Исполнено', 'Принято', 'Отменена']

const STATUSES = { active: EXECUTOR_ACTIVE_STATUSES, archive: EXECUTOR_ARCHIVE_STATUSES }

/**
 * Назначенные исполнителю заявки одной выборки — активные или архивные.
 *
 * Статусы фильтрует СЕРВЕР (повторяемый `status=…`): раньше грузились
 * последние 50 любых, и при длинном архиве старые активные выпадали из
 * выборки. Ключ `['twa','executor-tasks', scope]` — префикс прежнего, так что
 * `invalidateQueries({ queryKey: ['twa','executor-tasks'] })` обновляет оба.
 */
export function useExecutorTasks(scope: 'active' | 'archive'): UseQueryResult<TwaRequest[]> {
  return useQuery<TwaRequest[]>({
    queryKey: ['twa', 'executor-tasks', scope],
    queryFn: () => twaClient.get('/api/v2/requests', {
      params: { view: 'assigned', status: STATUSES[scope], limit: 50 },
      paramsSerializer: { indexes: null },
    }).then(r => r.data),
    staleTime: 30_000,
  })
}
