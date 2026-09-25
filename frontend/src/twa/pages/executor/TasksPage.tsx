import { useQuery } from '@tanstack/react-query'
import type { TwaRequest } from '../../types'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import { tStatus } from '../../../i18n/apiMaps'
import RequestCard from '../../components/RequestCard'
import { CardSkeleton } from '../../components/Skeleton'
import PullToRefresh from '../../components/PullToRefresh'
import QueryErrorState from '../../components/QueryErrorState'

// «Возвращена» — житель вернул работу; решает менеджер (вернуть в работу /
// принять / отменить), у исполнителя действий нет. Первой — чтобы заметили.
const RETURNED = 'Возвращена'

export default function TasksPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const { data: requests = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['twa', 'executor-tasks'],
    queryFn: () => twaClient.get('/api/v2/requests', {
      params: { view: 'assigned', limit: 50 }
    }).then(r => r.data),
    staleTime: 30_000,
  })

  const activeStatuses = [RETURNED, 'В работе', 'Закуп', 'Уточнение', 'Новая']
  const active = requests.filter((r: TwaRequest) => activeStatuses.includes(r.status))

  // Group by status
  const grouped = activeStatuses.reduce((acc: Record<string, TwaRequest[]>, status) => {
    const items = active.filter((r: TwaRequest) => r.status === status)
    if (items.length > 0) acc[status] = items
    return acc
  }, {})

  return (
    <PullToRefresh queryKeys={[['twa', 'executor-tasks']]}>
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.tasks.title')}</h1>

      {isLoading && <CardSkeleton />}

      {isError && <QueryErrorState onRetry={() => refetch()} />}

      {!isLoading && !isError && active.length === 0 && (
        <div className="text-center py-12">
          <p className="text-[40px] mb-2">📋</p>
          <p className="text-gray-400 text-[14px]">{t('twa.exec.tasks.empty')}</p>
        </div>
      )}

      {Object.entries(grouped).map(([status, items]) => (
        <div key={status} className="mb-4">
          <h2 className={`text-[12px] font-semibold uppercase mb-2 ${status === RETURNED ? 'text-orange-600 dark:text-orange-400' : 'text-gray-500'}`}>{tStatus(status, t)} ({items.length})</h2>
          {status === RETURNED && (
            <p className="text-[12px] text-orange-700 dark:text-orange-300 mb-2">{t('twa.exec.tasks.returnedHint')}</p>
          )}
          {items.map((req: TwaRequest) => (
            <div key={req.request_number}>
              <RequestCard
                requestNumber={req.request_number}
                status={req.status}
                category={req.category}
                description={req.description}
                createdAt={req.created_at}
                onClick={() => navigate(`/twa/exec/tasks/${req.request_number}`)}
              />
              {status === RETURNED && req.return_reason && (
                <p className="-mt-1 mb-2 px-3.5 text-[12px] text-orange-700 dark:text-orange-300">
                  {t('twa.exec.tasks.returnReason')}: {req.return_reason}
                </p>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
    </PullToRefresh>
  )
}
