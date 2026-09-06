import { useState } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ArrowUpDown, CalendarDays, Plus, Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { usePageTitle } from '../../hooks/usePageTitle'
import { useHasRole } from '../../hooks/useHasRole'
import { useElevators, useElevatorsSummary } from '../../hooks/useElevators'
import AccessPagination from '../../components/access/AccessPagination'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import ElevatorSummaryCards from '../../components/elevators/ElevatorSummaryCards'
import ElevatorFilters from '../../components/elevators/ElevatorFilters'
import ElevatorTable from '../../components/elevators/ElevatorTable'
import type { ElevatorListFilters } from '../../types/elevators'

/**
 * Реестр лифтов (/dashboard/elevators): сводка, фильтры, таблица, пагинация.
 * Читают manager и executor; «Добавить лифт» и «Настройки» — только manager.
 */
const PAGE_LIMIT = 50

export default function ElevatorsPage() {
  const { t } = useTranslation()
  usePageTitle(t('elevators.title'))
  const isManager = useHasRole('manager')
  const [filters, setFilters] = useState<ElevatorListFilters>({ limit: PAGE_LIMIT, offset: 0 })

  const summary = useElevatorsSummary()
  const list = useElevators(filters)

  const patchFilters = (patch: Partial<ElevatorListFilters>) =>
    setFilters((prev) => ({ ...prev, ...patch, offset: 0 }))

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <ArrowUpDown className="text-accent" size={22} />
          <div>
            <h1 className="text-xl font-semibold text-text-primary">{t('elevators.title')}</h1>
            <p className="text-[13px] text-text-muted">{t('elevators.subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/dashboard/elevators/calendar"><CalendarDays size={15} /> {t('elevators.actions.calendar')}</Link>
          </Button>
          {isManager && (
            <>
              <Button asChild variant="outline" size="sm">
                <Link to="/dashboard/elevators/config"><Settings size={15} /> {t('elevators.actions.config')}</Link>
              </Button>
              <Button asChild size="sm">
                <Link to="/dashboard/elevators/new"><Plus size={15} /> {t('elevators.actions.add')}</Link>
              </Button>
            </>
          )}
        </div>
      </div>

      {summary.data && <ElevatorSummaryCards summary={summary.data} />}

      <ElevatorFilters filters={filters} onChange={patchFilters} />

      {list.isLoading ? (
        <LoadingSpinner />
      ) : list.isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        <>
          <ElevatorTable items={list.data?.items ?? []} />
          <AccessPagination
            total={list.data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((prev) => ({ ...prev, offset }))}
          />
        </>
      )}
    </div>
  )
}
