import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Building2, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { usePageTitle } from '../../hooks/usePageTitle'
import { useHasRole } from '../../hooks/useHasRole'
import { useCommissionElevator, useElevator } from '../../hooks/useElevators'
import AccessTabBar from '../../components/access/AccessTabBar'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import EmptyState from '../../components/shared/EmptyState'
import ElevatorStatusBadge from '../../components/elevators/ElevatorStatusBadge'
import ElevatorPassportTab from '../../components/elevators/ElevatorPassportTab'
import ElevatorStatusTab from '../../components/elevators/ElevatorStatusTab'
import ElevatorEventsTab from '../../components/elevators/ElevatorEventsTab'
import ElevatorCalendarTab from '../../components/elevators/ElevatorCalendarTab'
import ElevatorRequestsTab from '../../components/elevators/ElevatorRequestsTab'
import ArchiveDialog from '../../components/elevators/ArchiveDialog'
import { fmtInstant } from '../../utils/elevatorsFormat'

/**
 * Карточка лифта: шапка (label, адрес, статус, счётчик квартир без подъезда) +
 * вкладки Паспорт | Статус | Журнал | Календарь | Заявки. Правки — manager;
 * смена статуса и «Выполнено» в графике — executor и manager.
 */
type Tab = 'passport' | 'status' | 'events' | 'calendar' | 'requests'

export default function ElevatorDetailPage() {
  const { t } = useTranslation()
  const { id: idParam } = useParams<{ id: string }>()
  const id = Number(idParam)
  const isManager = useHasRole('manager')
  const [tab, setTab] = useState<Tab>('passport')
  const [archiveOpen, setArchiveOpen] = useState(false)

  const detail = useElevator(Number.isFinite(id) ? id : null)
  const commission = useCommissionElevator(id)
  usePageTitle(detail.data ? `${t('elevators.title')} · ${detail.data.label}` : t('elevators.title'))

  if (detail.isLoading) return <LoadingSpinner />
  if (detail.isError || !detail.data) {
    return (
      <div className="p-6">
        <EmptyState icon="🛗" title={t('elevators.detail.notFound')} />
      </div>
    )
  }
  const e = detail.data

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Button asChild variant="outline" size="sm">
            <Link to="/dashboard/elevators" aria-label={t('elevators.actions.backToList')}><ArrowLeft size={15} /></Link>
          </Button>
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-text-primary">{e.label}</h1>
              <ElevatorStatusBadge status={e.current_status} />
              {e.archived_at && (
                <span className="rounded-full bg-bg-surface text-text-muted text-[11px] px-2 py-0.5">
                  {t('elevators.detail.archived', { date: fmtInstant(e.archived_at) })}
                </span>
              )}
            </div>
            <p className="text-[13px] text-text-muted flex items-center gap-1.5">
              <Building2 size={14} /> {e.building_address}{e.yard_name ? ` · ${e.yard_name}` : ''}
            </p>
            {e.apartments_without_entrance_count > 0 && (
              <p
                className="text-[12px] text-orange flex items-center gap-1.5"
                title={t('elevators.detail.apartmentsWithoutEntranceHint')}
              >
                <TriangleAlert size={13} />
                {t('elevators.detail.apartmentsWithoutEntrance', { count: e.apartments_without_entrance_count })}
                <span className="text-text-muted">— {t('elevators.detail.apartmentsWithoutEntranceHint')}</span>
              </p>
            )}
          </div>
        </div>
        <div className="text-[13px] text-text-muted">
          {t('elevators.detail.openRequests')}: <span className="font-semibold text-text-primary">{e.open_requests_count}</span>
        </div>
      </div>

      <AccessTabBar
        tabs={[
          { key: 'passport', label: t('elevators.tabs.passport') },
          { key: 'status', label: t('elevators.tabs.status') },
          { key: 'events', label: t('elevators.tabs.events') },
          { key: 'calendar', label: t('elevators.tabs.calendar') },
          { key: 'requests', label: t('elevators.tabs.requests'), badge: e.open_requests_count || undefined },
        ]}
        active={tab}
        onChange={(key) => setTab(key as Tab)}
      />

      {tab === 'passport' && (
        <ElevatorPassportTab
          elevator={e}
          canWrite={isManager}
          onCommission={() => commission.mutate(null)}
          commissionPending={commission.isPending}
          onArchive={() => setArchiveOpen(true)}
        />
      )}
      {tab === 'status' && <ElevatorStatusTab elevator={e} />}
      {tab === 'events' && <ElevatorEventsTab elevatorId={e.id} />}
      {tab === 'calendar' && <ElevatorCalendarTab elevatorId={e.id} canWrite={isManager} />}
      {tab === 'requests' && <ElevatorRequestsTab elevator={e} canWrite={isManager} />}

      <ArchiveDialog elevatorId={e.id} open={archiveOpen} onClose={() => setArchiveOpen(false)} />
    </div>
  )
}
