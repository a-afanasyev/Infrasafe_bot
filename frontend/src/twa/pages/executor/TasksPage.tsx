import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import RequestCard from '../../components/RequestCard'
import { CardSkeleton } from '../../components/Skeleton'
import PullToRefresh from '../../components/PullToRefresh'

export default function TasksPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['twa', 'executor-tasks'],
    queryFn: () => twaClient.get('/api/v2/requests', {
      params: { scope: 'my', limit: 50 }
    }).then(r => r.data),
    staleTime: 30_000,
  })

  const activeStatuses = ['В работе', 'Закуп', 'Уточнение', 'Новая']
  const active = requests.filter((r: any) => activeStatuses.includes(r.status))

  // Group by status
  const grouped = activeStatuses.reduce((acc: Record<string, any[]>, status) => {
    const items = active.filter((r: any) => r.status === status)
    if (items.length > 0) acc[status] = items
    return acc
  }, {})

  return (
    <PullToRefresh queryKeys={[['twa', 'executor-tasks']]}>
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.tasks.title')}</h1>

      {isLoading && <CardSkeleton />}

      {!isLoading && active.length === 0 && (
        <div className="text-center py-12">
          <p className="text-[40px] mb-2">📋</p>
          <p className="text-gray-400 text-[14px]">{t('twa.exec.tasks.empty')}</p>
        </div>
      )}

      {Object.entries(grouped).map(([status, items]) => (
        <div key={status} className="mb-4">
          <h2 className="text-[12px] font-semibold text-gray-500 uppercase mb-2">{status} ({items.length})</h2>
          {items.map((req: any) => (
            <RequestCard
              key={req.request_number}
              requestNumber={req.request_number}
              status={req.status}
              category={req.category}
              description={req.description}
              createdAt={req.created_at}
              onClick={() => navigate(`/twa/exec/tasks/${req.request_number}`)}
            />
          ))}
        </div>
      ))}
    </div>
    </PullToRefresh>
  )
}
