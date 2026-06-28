import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck, KeyRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { usePageTitle } from '../../hooks/usePageTitle'
import RedeemCodeDialog from '../../components/access/RedeemCodeDialog'
import AccessTabBar from '../../components/access/AccessTabBar'
import AccessLiveFeed from '../../components/access/AccessLiveFeed'
import ManualReviewQueue from '../../components/access/ManualReviewQueue'
import AccessEventsTable from '../../components/access/AccessEventsTable'
import AccessEventsFilters from '../../components/access/AccessEventsFilters'
import AccessEventDetailDialog from '../../components/access/AccessEventDetailDialog'
import AccessPagination from '../../components/access/AccessPagination'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { useAccessEvents } from '../../hooks/useAccessRegistry'
import type { AccessEventsFilters as Filters } from '../../types/access'

/**
 * Экран «Пост охраны» (ТЗ access_control §9.6, §15.13).
 *
 * Вкладки: (а) Live-лента (WS, PD-safe), (б) Очередь ручной проверки
 * (manual_review) с действиями открыть/отказать, (в) История/поиск событий с
 * фильтрами и детализацией. Гард роутом/сайдбаром — ACCESS_MODULE_ROLES.
 */

const PAGE_LIMIT = 50
type Tab = 'live' | 'queue' | 'history'

function HistoryTab() {
  const [filters, setFilters] = useState<Filters>({ limit: PAGE_LIMIT, offset: 0 })
  const [detailId, setDetailId] = useState<number | null>(null)
  const { data, isLoading, isError } = useAccessEvents(filters)
  const { t } = useTranslation()

  const patch = (p: Partial<Filters>) => setFilters((prev) => ({ ...prev, ...p, offset: 0 }))

  return (
    <div className="flex flex-col gap-4">
      <AccessEventsFilters filters={filters} onChange={patch} />
      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        <>
          <AccessEventsTable events={data?.items ?? []} onRowClick={(e) => setDetailId(e.id)} />
          <AccessPagination
            total={data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((prev) => ({ ...prev, offset }))}
          />
        </>
      )}
      <AccessEventDetailDialog eventId={detailId} onClose={() => setDetailId(null)} />
    </div>
  )
}

export default function AccessControlPage() {
  const { t } = useTranslation()
  usePageTitle(t('accessControl.title'))
  const [tab, setTab] = useState<Tab>('live')
  const [queueDetailId, setQueueDetailId] = useState<number | null>(null)
  const [redeemOpen, setRedeemOpen] = useState(false)

  const tabs = [
    { key: 'live', label: t('accessControl.tabs.live') },
    { key: 'queue', label: t('accessControl.tabs.queue') },
    { key: 'history', label: t('accessControl.tabs.history') },
  ]

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="text-accent" size={22} />
          <div>
            <h1 className="text-xl font-semibold text-text-primary">{t('accessControl.title')}</h1>
            <p className="text-[13px] text-text-muted">{t('accessControl.subtitle')}</p>
          </div>
        </div>
        <Button onClick={() => setRedeemOpen(true)} className="shrink-0">
          <KeyRound size={16} className="mr-1.5" />
          {t('accessControl.redeem.action')}
        </Button>
      </div>

      <AccessTabBar tabs={tabs} active={tab} onChange={(k) => setTab(k as Tab)} />

      <RedeemCodeDialog open={redeemOpen} onClose={() => setRedeemOpen(false)} />

      {tab === 'live' && <AccessLiveFeed />}
      {tab === 'queue' && (
        <>
          <ManualReviewQueue onOpenDetail={(e) => setQueueDetailId(e.id)} />
          <AccessEventDetailDialog
            eventId={queueDetailId}
            onClose={() => setQueueDetailId(null)}
          />
        </>
      )}
      {tab === 'history' && <HistoryTab />}
    </div>
  )
}
