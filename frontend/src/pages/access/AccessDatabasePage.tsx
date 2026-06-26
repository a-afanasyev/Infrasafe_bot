import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database } from 'lucide-react'
import { usePageTitle } from '../../hooks/usePageTitle'
import AccessTabBar from '../../components/access/AccessTabBar'
import VehiclesTable from '../../components/access/VehiclesTable'
import VehicleDetailDialog from '../../components/access/VehicleDetailDialog'
import PassesTable from '../../components/access/PassesTable'
import RequestsTable from '../../components/access/RequestsTable'
import AccessPagination from '../../components/access/AccessPagination'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import {
  useAccessVehicles,
  useAccessPasses,
  useAccessRequests,
} from '../../hooks/useAccessRegistry'
import type {
  VehiclesFilters,
  PassesFilters,
  AccessRequestsFilters,
} from '../../types/access'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'

/**
 * Экран «База доступа» (менеджер, §6/§13). Табы: Автомобили / Пропуска / Заявки.
 * Гард — manager/system_admin (ACCESS_MANAGER_ROLES).
 */
const PAGE_LIMIT = 50
type Tab = 'vehicles' | 'passes' | 'requests'

// ── Автомобили ──────────────────────────────────────────────────────────────
function VehiclesPanel() {
  const { t } = useTranslation()
  const [filters, setFilters] = useState<VehiclesFilters>({ limit: PAGE_LIMIT, offset: 0 })
  const [detailId, setDetailId] = useState<number | null>(null)
  const { data, isLoading, isError } = useAccessVehicles(filters)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[11px] text-text-muted">
          {t('accessControl.vehicles.plate')}
          <Input
            type="text"
            value={filters.plate ?? ''}
            onChange={(e) =>
              setFilters((p) => ({ ...p, plate: e.target.value || undefined, offset: 0 }))
            }
            placeholder={t('accessControl.filters.platePlaceholder')}
            className="w-[180px]"
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-text-muted">
          {t('accessControl.columns.status')}
          <Select
            value={filters.status ?? ''}
            onChange={(e) =>
              setFilters((p) => ({ ...p, status: e.target.value || undefined, offset: 0 }))
            }
            className="w-[160px]"
          >
            <option value="">{t('accessControl.filters.allStatuses')}</option>
            {['active', 'blocked'].map((s) => (
              <option key={s} value={s}>
                {t(`accessControl.status.${s}`, { defaultValue: s })}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        <>
          <VehiclesTable vehicles={data?.items ?? []} onRowClick={(v) => setDetailId(v.id)} />
          <AccessPagination
            total={data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((p) => ({ ...p, offset }))}
          />
        </>
      )}

      <VehicleDetailDialog vehicleId={detailId} onClose={() => setDetailId(null)} />
    </div>
  )
}

// ── Пропуска ────────────────────────────────────────────────────────────────
function PassesPanel() {
  const { t } = useTranslation()
  const [filters, setFilters] = useState<PassesFilters>({ limit: PAGE_LIMIT, offset: 0 })
  const { data, isLoading, isError } = useAccessPasses(filters)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[11px] text-text-muted">
          {t('accessControl.columns.status')}
          <Select
            value={filters.status ?? ''}
            onChange={(e) =>
              setFilters((p) => ({ ...p, status: e.target.value || undefined, offset: 0 }))
            }
            className="w-[160px]"
          >
            <option value="">{t('accessControl.filters.allStatuses')}</option>
            {['active', 'expired', 'revoked'].map((s) => (
              <option key={s} value={s}>
                {t(`accessControl.status.${s}`, { defaultValue: s })}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        <>
          <PassesTable passes={data?.items ?? []} />
          <AccessPagination
            total={data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((p) => ({ ...p, offset }))}
          />
        </>
      )}
    </div>
  )
}

// ── Заявки ──────────────────────────────────────────────────────────────────
function RequestsPanel() {
  const { t } = useTranslation()
  const [filters, setFilters] = useState<AccessRequestsFilters>({ limit: PAGE_LIMIT, offset: 0 })
  const { data, isLoading, isError } = useAccessRequests(filters)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[11px] text-text-muted">
          {t('accessControl.columns.status')}
          <Select
            value={filters.status ?? ''}
            onChange={(e) =>
              setFilters((p) => ({ ...p, status: e.target.value || undefined, offset: 0 }))
            }
            className="w-[160px]"
          >
            <option value="">{t('accessControl.filters.allStatuses')}</option>
            {['pending', 'approved', 'rejected'].map((s) => (
              <option key={s} value={s}>
                {t(`accessControl.status.${s}`, { defaultValue: s })}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        <>
          <RequestsTable requests={data?.items ?? []} />
          <AccessPagination
            total={data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((p) => ({ ...p, offset }))}
          />
        </>
      )}
    </div>
  )
}

export default function AccessDatabasePage() {
  const { t } = useTranslation()
  usePageTitle(t('accessControl.database.title'))
  const [tab, setTab] = useState<Tab>('vehicles')

  const tabs = [
    { key: 'vehicles', label: t('accessControl.database.vehicles') },
    { key: 'passes', label: t('accessControl.database.passes') },
    { key: 'requests', label: t('accessControl.database.requests') },
  ]

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-center gap-2.5">
        <Database className="text-accent" size={22} />
        <div>
          <h1 className="text-xl font-semibold text-text-primary">
            {t('accessControl.database.title')}
          </h1>
          <p className="text-[13px] text-text-muted">{t('accessControl.database.subtitle')}</p>
        </div>
      </div>

      <AccessTabBar tabs={tabs} active={tab} onChange={(k) => setTab(k as Tab)} />

      {tab === 'vehicles' && <VehiclesPanel />}
      {tab === 'passes' && <PassesPanel />}
      {tab === 'requests' && <RequestsPanel />}
    </div>
  )
}
