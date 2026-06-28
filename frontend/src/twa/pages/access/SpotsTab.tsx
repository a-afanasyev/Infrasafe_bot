import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { SquareParking } from 'lucide-react'
import { twaClient } from '../../twaClient'
import { CardSkeleton } from '../../components/Skeleton'
import PullToRefresh from '../../components/PullToRefresh'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import {
  ACCESS_BASE,
  formatDateTime,
  type SpotAssignmentRow,
  type SpotAssignmentsPage,
} from './types'

/**
 * Под-вид «Моё место» (§6.4, §10.3): закрепления парковочных мест квартир жителя.
 *
 * Карточка: код места, зона, тип владения (+срок для аренды), занятость «X из Y»
 * и переключатель «Ограничение на лишние авто» (тумблер enforce_limit). Выключение
 * временно пускает вторую машину (POST /my/spot-assignments/{id}/toggle-limit).
 */
export default function SpotsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()

  const spotsQuery = useQuery<SpotAssignmentsPage>({
    queryKey: ['twa', 'access', 'spots'],
    queryFn: () => twaClient.get(`${ACCESS_BASE}/my/spots`).then((r) => r.data),
    staleTime: 30_000,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      twaClient
        .post(`${ACCESS_BASE}/my/spot-assignments/${id}/toggle-limit`, { enabled })
        .then((r) => r.data),
    onSuccess: (_data, vars) => {
      haptic('notification')
      toast.success(
        vars.enabled
          ? t('twa.access.spots.limitOn')
          : t('twa.access.spots.limitOff'),
      )
      queryClient.invalidateQueries({ queryKey: ['twa', 'access', 'spots'] })
    },
    onError: (err: unknown) => notifyError(err),
  })

  const spots = spotsQuery.data?.items ?? []

  const ownershipLabel = (a: SpotAssignmentRow) => {
    const key = `twa.access.spots.ownershipType.${a.ownership_type}`
    const translated = t(key)
    return translated === key ? a.ownership_type : translated
  }

  return (
    <PullToRefresh queryKeys={[['twa', 'access', 'spots']]}>
      {spotsQuery.isError && (
        <p className="text-[13px] text-red-500 mb-3">{t('twa.access.error')}</p>
      )}

      {spotsQuery.isLoading && <CardSkeleton />}

      {!spotsQuery.isLoading && spots.length === 0 && (
        <div className="text-center py-8">
          <p className="text-gray-400 text-[14px]">{t('twa.access.spots.empty')}</p>
        </div>
      )}

      <div className="space-y-2">
        {spots.map((a) => (
          <div
            key={a.id}
            className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <SquareParking size={16} className="text-emerald-500 shrink-0" />
                <span className="font-semibold text-[14px] text-gray-900 dark:text-gray-100 truncate">
                  {a.spot_code}
                </span>
              </div>
              <span className="text-[12px] text-gray-500 dark:text-gray-400">
                {t('twa.access.spots.occupiedOf', { occupied: a.occupied, spots: a.spots })}
              </span>
            </div>

            <p className="text-[12px] text-gray-500 dark:text-gray-400 mt-1">
              {a.zone_name} · {ownershipLabel(a)}
            </p>
            {a.ownership_type === 'rented' && a.valid_until && (
              <p className="text-[12px] text-gray-500 dark:text-gray-400">
                {t('twa.access.spots.validUntil')}: {formatDateTime(a.valid_until)}
              </p>
            )}

            {/* Тумблер «Ограничение на лишние авто» (§10.3). */}
            <div className="mt-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-gray-900 dark:text-gray-100">
                  {t('twa.access.spots.enforceLimit')}
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  {t('twa.access.spots.enforceLimitHint')}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={a.enforce_limit}
                aria-label={t('twa.access.spots.enforceLimit')}
                disabled={toggleMutation.isPending}
                onClick={() => toggleMutation.mutate({ id: a.id, enabled: !a.enforce_limit })}
                className={`relative shrink-0 inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                  a.enforce_limit ? 'bg-emerald-500' : 'bg-gray-300 dark:bg-gray-600'
                }`}
              >
                <span
                  className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                    a.enforce_limit ? 'translate-x-5' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </div>
          </div>
        ))}
      </div>
    </PullToRefresh>
  )
}
