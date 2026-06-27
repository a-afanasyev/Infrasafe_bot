import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { History } from 'lucide-react'
import { usePageTitle } from '../../hooks/usePageTitle'
import AccessEventsTable from '../../components/access/AccessEventsTable'
import AccessEventsFilters from '../../components/access/AccessEventsFilters'
import AccessEventDetailDialog from '../../components/access/AccessEventDetailDialog'
import AccessPagination from '../../components/access/AccessPagination'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { useAccessEvents } from '../../hooks/useAccessRegistry'
import type { AccessEventsFilters as Filters } from '../../types/access'

/**
 * Экран «История проездов» (менеджер, §6/§13.2). Таблица событий с расширенными
 * фильтрами (период, решение, зона, номер, источник), пагинацией и деталью.
 * Гард — manager/system_admin (ACCESS_MANAGER_ROLES).
 */
const PAGE_LIMIT = 50

export default function AccessHistoryPage() {
  const { t } = useTranslation()
  usePageTitle(t('accessControl.history.title'))
  const [filters, setFilters] = useState<Filters>({ limit: PAGE_LIMIT, offset: 0 })
  const [detailId, setDetailId] = useState<number | null>(null)
  const { data, isLoading, isError } = useAccessEvents(filters)

  const patch = (p: Partial<Filters>) => setFilters((prev) => ({ ...prev, ...p, offset: 0 }))

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-center gap-2.5">
        <History className="text-accent" size={22} />
        <div>
          <h1 className="text-xl font-semibold text-text-primary">
            {t('accessControl.history.title')}
          </h1>
          <p className="text-[13px] text-text-muted">{t('accessControl.history.subtitle')}</p>
        </div>
      </div>

      <AccessEventsFilters filters={filters} onChange={patch} extended />

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
