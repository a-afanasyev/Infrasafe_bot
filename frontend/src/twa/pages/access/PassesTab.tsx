import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Ticket, PlusCircle } from 'lucide-react'
import { twaClient } from '../../twaClient'
import { CardSkeleton } from '../../components/Skeleton'
import PullToRefresh from '../../components/PullToRefresh'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import {
  ACCESS_BASE,
  formatDateTime,
  statusBadgeClass,
  type AccessPage,
  type PassRow,
} from './types'

export default function PassesTab() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()

  const passesQuery = useQuery<AccessPage<PassRow>>({
    queryKey: ['twa', 'access', 'passes'],
    queryFn: () => twaClient.get(`${ACCESS_BASE}/my/passes`).then((r) => r.data),
    staleTime: 30_000,
  })

  const cancelMutation = useMutation({
    mutationFn: (passId: number) =>
      twaClient.post(`${ACCESS_BASE}/passes/${passId}/cancel`).then((r) => r.data),
    onSuccess: () => {
      haptic('notification')
      toast.success(t('twa.access.passes.canceled'))
      queryClient.invalidateQueries({ queryKey: ['twa', 'access', 'passes'] })
    },
    onError: (err: unknown) => notifyError(err),
  })

  const passes = passesQuery.data?.items ?? []

  const passTypeLabel = (s: string) => {
    const key = `twa.access.passType.${s}`
    const translated = t(key)
    return translated === key ? s : translated
  }
  const passStatusLabel = (s: string) => {
    const key = `twa.access.passStatus.${s}`
    const translated = t(key)
    return translated === key ? s : translated
  }

  const onCancel = (passId: number) => {
    if (window.confirm(t('twa.access.passes.cancelConfirm'))) {
      cancelMutation.mutate(passId)
    }
  }

  return (
    <PullToRefresh queryKeys={[['twa', 'access', 'passes']]}>
      <button
        onClick={() => navigate('/twa/app/access/pass-new')}
        className="w-full flex items-center justify-center gap-2 bg-emerald-500 text-white py-3 rounded-xl font-medium mb-4 active:scale-[0.98] transition-transform"
      >
        <PlusCircle size={18} />
        {t('twa.access.passes.newButton')}
      </button>

      {passesQuery.isError && (
        <p className="text-[13px] text-red-500 mb-3">{t('twa.access.error')}</p>
      )}

      {passesQuery.isLoading && <CardSkeleton />}

      {!passesQuery.isLoading && passes.length === 0 && (
        <div className="text-center py-8">
          <p className="text-gray-400 text-[14px]">{t('twa.access.passes.empty')}</p>
        </div>
      )}

      <div className="space-y-2">
        {passes.map((p) => (
          <div
            key={p.id}
            className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Ticket size={16} className="text-emerald-500 shrink-0" />
                <span className="font-semibold text-[14px] text-gray-900 dark:text-gray-100 truncate">
                  {passTypeLabel(p.pass_type)}
                </span>
              </div>
              <span
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${statusBadgeClass(p.status)}`}
              >
                {passStatusLabel(p.status)}
              </span>
            </div>

            {p.plate_number_original && (
              <p className="text-[12px] text-gray-600 dark:text-gray-300 mt-1">
                {p.plate_number_original}
              </p>
            )}
            <p className="text-[12px] text-gray-500 dark:text-gray-400 mt-1">
              {t('twa.access.passes.validUntil')}: {formatDateTime(p.valid_until)}
            </p>
            <p className="text-[12px] text-gray-500 dark:text-gray-400">
              {t('twa.access.passes.entries')}: {p.used_entries}/{p.max_entries}
            </p>

            {p.status === 'active' && (
              <button
                onClick={() => onCancel(p.id)}
                disabled={cancelMutation.isPending}
                className="mt-3 w-full text-[13px] font-medium text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 rounded-xl py-2 disabled:opacity-50"
              >
                {t('twa.access.passes.cancel')}
              </button>
            )}
          </div>
        ))}
      </div>
    </PullToRefresh>
  )
}
