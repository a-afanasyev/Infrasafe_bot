import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import RequestCard from '../../components/RequestCard'
import { CardSkeleton } from '../../components/Skeleton'

export default function PurchasePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['executor-tasks'],
    queryFn: () => twaClient.get('/api/v2/requests', {
      params: { scope: 'my', limit: 50 }
    }).then(r => r.data),
    staleTime: 30_000,
  })

  // TWA-29: inline "back to work" so the executor doesn't have to drill into
  // detail just to flip a purchase item back. Same transition the detail page
  // uses; we track the in-flight number to disable only that card's button.
  const backToWork = useMutation({
    mutationFn: (num: string) => twaClient.patch(`/api/v2/requests/${num}`, { status: 'В работе' }),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['executor-tasks'] })
    },
    onError: (err: unknown) => {
      haptic('notification')
      notifyError(err, 'Не удалось изменить статус')
    },
  })

  const purchases = requests.filter((r: any) => r.status === 'Закуп')

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.purchase.title')}</h1>

      {isLoading && <CardSkeleton />}

      {!isLoading && purchases.length === 0 && (
        <div className="text-center py-12">
          <p className="text-[40px] mb-2">🛒</p>
          <p className="text-gray-400 text-[14px]">{t('twa.exec.purchase.empty')}</p>
        </div>
      )}

      {purchases.map((req: any) => (
        <div key={req.request_number} className="mb-2">
          <RequestCard
            requestNumber={req.request_number}
            status={req.status}
            category={req.category}
            description={req.requested_materials || req.description}
            createdAt={req.created_at}
            onClick={() => navigate(`/twa/exec/tasks/${req.request_number}`)}
          />
          <button
            onClick={() => backToWork.mutate(req.request_number)}
            disabled={backToWork.isPending && backToWork.variables === req.request_number}
            className="w-full -mt-1 flex items-center justify-center gap-1 bg-emerald-500 text-white py-2.5 rounded-xl text-[13px] font-semibold disabled:opacity-50"
          >
            <ArrowLeft size={15} /> {t('twa.exec.detail.backToWork')}
          </button>
        </div>
      ))}
    </div>
  )
}
