import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { twaClient } from '../../twaClient'
import { CardSkeleton } from '../../components/Skeleton'
import PullToRefresh from '../../components/PullToRefresh'
import {
  ACCESS_BASE,
  formatDateTime,
  type AccessEventRow,
  type AccessPage,
} from './types'

export default function EventsTab() {
  const { t } = useTranslation()

  const eventsQuery = useQuery<AccessPage<AccessEventRow>>({
    queryKey: ['twa', 'access', 'events'],
    queryFn: () => twaClient.get(`${ACCESS_BASE}/my/events`).then((r) => r.data),
    staleTime: 30_000,
  })

  const events = eventsQuery.data?.items ?? []

  const isInbound = (dir: string) => dir === 'in' || dir === 'entry' || dir === 'inbound'
  const isAllow = (decision: string | null) =>
    decision === 'allow' || decision === 'allowed' || decision === 'granted'

  return (
    <PullToRefresh queryKeys={[['twa', 'access', 'events']]}>
      {eventsQuery.isError && (
        <p className="text-[13px] text-red-500 mb-3">{t('twa.access.error')}</p>
      )}

      {eventsQuery.isLoading && <CardSkeleton />}

      {!eventsQuery.isLoading && events.length === 0 && (
        <div className="text-center py-8">
          <p className="text-gray-400 text-[14px]">{t('twa.access.events.empty')}</p>
        </div>
      )}

      <div className="space-y-2">
        {events.map((e) => {
          const inbound = isInbound(e.direction)
          const allow = isAllow(e.decision)
          return (
            <div
              key={e.id}
              className="bg-white dark:bg-gray-800 rounded-2xl p-3 border border-gray-100 dark:border-gray-700"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  {inbound ? (
                    <ArrowDownLeft size={16} className="text-emerald-500 shrink-0" />
                  ) : (
                    <ArrowUpRight size={16} className="text-blue-500 shrink-0" />
                  )}
                  <span className="font-medium text-[13px] text-gray-900 dark:text-gray-100 truncate">
                    {e.plate_number_normalized || '—'}
                  </span>
                </div>
                {e.decision && (
                  <span
                    className={`text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${
                      allow
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                    }`}
                  >
                    {allow ? t('twa.access.events.allow') : t('twa.access.events.deny')}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                {inbound ? t('twa.access.events.in') : t('twa.access.events.out')} ·{' '}
                {formatDateTime(e.occurred_at)}
              </p>
            </div>
          )
        })}
      </div>
    </PullToRefresh>
  )
}
