import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import RequestCard from '../../components/RequestCard'

export default function RequestsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<'active' | 'archive'>('active')

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['my-requests'],
    queryFn: () => twaClient.get('/api/v2/requests', {
      params: { scope: 'my', limit: 50 }
    }).then(r => r.data),
    staleTime: 30_000,
  })

  const activeStatuses = ['Новая', 'В работе', 'Закуп', 'Уточнение']
  const filtered = requests.filter((r: any) =>
    filter === 'active'
      ? activeStatuses.includes(r.status)
      : !activeStatuses.includes(r.status)
  )

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-3">{t('twa.requests.title')}</h1>

      <div className="flex gap-2 mb-4">
        {(['active', 'archive'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-1.5 rounded-full text-[13px] font-medium transition-colors ${
              filter === f
                ? 'bg-emerald-500 text-white'
                : 'bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
            }`}
          >
            {t(`twa.requests.${f}`)}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-center text-gray-400 py-8">{t('common.loading')}</p>}

      {!isLoading && filtered.length === 0 && (
        <div className="text-center py-12">
          <p className="text-gray-400 text-[14px]">{t('twa.requests.empty')}</p>
        </div>
      )}

      {filtered.map((req: any) => (
        <RequestCard
          key={req.request_number}
          requestNumber={req.request_number}
          status={req.status}
          category={req.category}
          description={req.description}
          executorName={req.executor_name}
          createdAt={req.created_at}
          onClick={() => navigate(`/twa/app/requests/${req.request_number}`)}
        />
      ))}
    </div>
  )
}
