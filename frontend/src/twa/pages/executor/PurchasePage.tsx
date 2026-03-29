import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import RequestCard from '../../components/RequestCard'

export default function PurchasePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['executor-tasks'],
    queryFn: () => twaClient.get('/api/v2/requests', {
      params: { scope: 'my', limit: 50 }
    }).then(r => r.data),
    staleTime: 30_000,
  })

  const purchases = requests.filter((r: any) => r.status === 'Закуп')

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.purchase.title')}</h1>

      {isLoading && <p className="text-center text-gray-400 py-8">{t('common.loading')}</p>}

      {!isLoading && purchases.length === 0 && (
        <div className="text-center py-12">
          <p className="text-[40px] mb-2">🛒</p>
          <p className="text-gray-400 text-[14px]">{t('twa.exec.purchase.empty')}</p>
        </div>
      )}

      {purchases.map((req: any) => (
        <RequestCard
          key={req.request_number}
          requestNumber={req.request_number}
          status={req.status}
          category={req.category}
          description={req.requested_materials || req.description}
          createdAt={req.created_at}
          onClick={() => navigate(`/twa/exec/tasks/${req.request_number}`)}
        />
      ))}
    </div>
  )
}
