import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import { tCategory, tStatus } from '../../../i18n/apiMaps'
import StatusBadge from '../../components/StatusBadge'
import StarRating from '../../components/StarRating'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { CardSkeleton } from '../../components/Skeleton'

export default function AcceptancePage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [ratings, setRatings] = useState<Record<string, number>>({})

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['acceptance'],
    queryFn: () => twaClient.get('/api/v2/requests/acceptance').then(r => r.data),
    staleTime: 30_000,
  })

  const acceptMutation = useMutation({
    mutationFn: (num: string) => twaClient.patch(`/api/v2/requests/${num}`, {
      status: 'Принято',
      rating: ratings[num] || 0,
    }),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['acceptance'] })
      setExpanded(null)
    },
    onError: (err: any) => {
      console.error('Mutation failed:', err)
      // Toast would go here in the future
    },
  })

  const returnMutation = useMutation({
    mutationFn: (num: string) => twaClient.patch(`/api/v2/requests/${num}`, {
      status: 'В работе',
    }),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['acceptance'] })
      setExpanded(null)
    },
    onError: (err: any) => {
      console.error('Mutation failed:', err)
      // Toast would go here in the future
    },
  })

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.acceptance.title')}</h1>

      {isLoading && <CardSkeleton />}

      {!isLoading && requests.length === 0 && (
        <div className="text-center py-12">
          <p className="text-[40px] mb-2">✅</p>
          <p className="text-gray-400 text-[14px]">{t('twa.acceptance.empty')}</p>
        </div>
      )}

      {requests.map((req: any) => (
        <div key={req.request_number} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 mb-3 overflow-hidden">
          <div
            onClick={() => setExpanded(expanded === req.request_number ? null : req.request_number)}
            className="p-3.5 cursor-pointer active:bg-gray-50 dark:active:bg-gray-750"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-[11px] text-gray-400">{req.request_number}</span>
              <StatusBadge status={req.status} label={tStatus(req.status, t)} />
            </div>
            <div className="font-semibold text-[14px] text-gray-900 dark:text-gray-100">{tCategory(req.category, t)}</div>
            {req.description && <p className="text-[12px] text-gray-500 line-clamp-1 mt-0.5">{req.description}</p>}
          </div>

          {expanded === req.request_number && (
            <div className="px-3.5 pb-3.5 border-t border-gray-100 dark:border-gray-700 pt-3">
              <p className="text-[12px] text-gray-600 dark:text-gray-400 mb-3">{t('twa.acceptance.rateWork')}</p>
              <StarRating value={ratings[req.request_number] || 0} onChange={(v) => setRatings(prev => ({ ...prev, [req.request_number]: v }))} />

              <div className="flex gap-2 mt-4">
                <button
                  disabled={!ratings[req.request_number] || acceptMutation.isPending}
                  onClick={() => acceptMutation.mutate(req.request_number)}
                  className="flex-1 bg-emerald-500 text-white py-2.5 rounded-xl text-[13px] font-semibold disabled:opacity-40"
                >
                  {t('twa.acceptance.accept')}
                </button>
                <button
                  onClick={() => returnMutation.mutate(req.request_number)}
                  disabled={returnMutation.isPending}
                  className="flex-1 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 py-2.5 rounded-xl text-[13px] font-medium"
                >
                  {t('twa.acceptance.return')}
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
