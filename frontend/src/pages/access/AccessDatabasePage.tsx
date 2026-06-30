import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database, Plus } from 'lucide-react'
import { usePageTitle } from '../../hooks/usePageTitle'
import AccessTabBar from '../../components/access/AccessTabBar'
import VehiclesTable from '../../components/access/VehiclesTable'
import VehicleDetailDialog from '../../components/access/VehicleDetailDialog'
import VehicleFormDialog from '../../components/access/VehicleFormDialog'
import VehicleEditDialog from '../../components/access/VehicleEditDialog'
import VehicleStatusDialog, {
  type StatusTarget,
} from '../../components/access/VehicleStatusDialog'
import TaxiPassFormDialog from '../../components/access/TaxiPassFormDialog'
import PassesTable from '../../components/access/PassesTable'
import PassDetailDialog from '../../components/access/PassDetailDialog'
import RequestsTable from '../../components/access/RequestsTable'
import RequestDetailDialog from '../../components/access/RequestDetailDialog'
import RequestReviewDialog, {
  type ReviewTarget,
} from '../../components/access/RequestReviewDialog'
import AccessPagination from '../../components/access/AccessPagination'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import {
  useAccessVehicles,
  useAccessPasses,
  useAccessRequests,
  useCreateVehicle,
  useUpdateVehicleStatus,
  useUpdateVehicle,
  useCreateTaxiPass,
  useReviewRequest,
} from '../../hooks/useAccessRegistry'
import { useHasAnyRole } from '../../hooks/useHasRole'
import { ACCESS_MANAGER_ROLES } from '../../constants/roles'
import type {
  VehiclesFilters,
  PassesFilters,
  AccessRequestsFilters,
  VehicleRow,
} from '../../types/access'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'

/**
 * Экран «База доступа» (менеджер, §6/§13). Табы: Автомобили / Пропуска / Заявки.
 * Гард — manager/system_admin (ACCESS_MANAGER_ROLES). Действия (создание/блок/
 * рассмотрение) рендерятся только для этих ролей (useHasAnyRole), хотя route уже
 * закрыт тем же набором — двойная страховка от чужого UI.
 */
const PAGE_LIMIT = 50
type Tab = 'vehicles' | 'passes' | 'requests'

// ── Автомобили ──────────────────────────────────────────────────────────────
function VehiclesPanel({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation()
  const [filters, setFilters] = useState<VehiclesFilters>({ limit: PAGE_LIMIT, offset: 0 })
  const [detailId, setDetailId] = useState<number | null>(null)
  const [editId, setEditId] = useState<number | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [statusTarget, setStatusTarget] = useState<StatusTarget | null>(null)
  const { data, isLoading, isError } = useAccessVehicles(filters)

  const createVehicle = useCreateVehicle()
  const updateStatus = useUpdateVehicleStatus()
  const updateVehicle = useUpdateVehicle()

  const rowActions = canManage
    ? {
        onBlock: (v: VehicleRow) => setStatusTarget({ vehicle: v, status: 'blocked' as const }),
        onUnblock: (v: VehicleRow) => setStatusTarget({ vehicle: v, status: 'active' as const }),
        onArchive: (v: VehicleRow) => setStatusTarget({ vehicle: v, status: 'archived' as const }),
      }
    : undefined

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
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
              {['active', 'blocked', 'archived'].map((s) => (
                <option key={s} value={s}>
                  {t(`accessControl.status.${s}`, { defaultValue: s })}
                </option>
              ))}
            </Select>
          </label>
        </div>
        {canManage && (
          <Button onClick={() => setFormOpen(true)} className="gap-1.5">
            <Plus size={16} />
            {t('accessControl.actions.addVehicle')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        <>
          <VehiclesTable
            vehicles={data?.items ?? []}
            onRowClick={(v) => setDetailId(v.id)}
            actions={rowActions}
          />
          <AccessPagination
            total={data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((p) => ({ ...p, offset }))}
          />
        </>
      )}

      <VehicleDetailDialog
        vehicleId={detailId}
        onClose={() => setDetailId(null)}
        onEdit={
          canManage
            ? () => {
                setEditId(detailId)
                setDetailId(null)
              }
            : undefined
        }
      />

      {canManage && (
        <>
          <VehicleEditDialog
            vehicleId={editId}
            loading={updateVehicle.isPending}
            onClose={() => setEditId(null)}
            onSubmit={(payload) => {
              if (editId === null) return
              updateVehicle.mutate(
                { vehicleId: editId, payload },
                { onSuccess: () => setEditId(null) },
              )
            }}
          />
          <VehicleFormDialog
            open={formOpen}
            loading={createVehicle.isPending}
            onClose={() => setFormOpen(false)}
            onSubmit={(payload) =>
              createVehicle.mutate(payload, { onSuccess: () => setFormOpen(false) })
            }
          />
          <VehicleStatusDialog
            target={statusTarget}
            loading={updateStatus.isPending}
            onClose={() => setStatusTarget(null)}
            onSubmit={({ status, reason }) => {
              if (!statusTarget) return
              updateStatus.mutate(
                { vehicleId: statusTarget.vehicle.id, payload: { status, reason } },
                { onSuccess: () => setStatusTarget(null) },
              )
            }}
          />
        </>
      )}
    </div>
  )
}

// ── Пропуска ────────────────────────────────────────────────────────────────
function PassesPanel({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation()
  const [filters, setFilters] = useState<PassesFilters>({ limit: PAGE_LIMIT, offset: 0 })
  const [formOpen, setFormOpen] = useState(false)
  const [passDetailId, setPassDetailId] = useState<number | null>(null)
  const { data, isLoading, isError } = useAccessPasses(filters)
  const createTaxiPass = useCreateTaxiPass()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
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
        {canManage && (
          <Button onClick={() => setFormOpen(true)} className="gap-1.5">
            <Plus size={16} />
            {t('accessControl.actions.createTaxiPass')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        <>
          <PassesTable passes={data?.items ?? []} onSelect={(p) => setPassDetailId(p.id)} />
          <AccessPagination
            total={data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((p) => ({ ...p, offset }))}
          />
        </>
      )}

      <PassDetailDialog
        passId={passDetailId}
        canManage={canManage}
        onClose={() => setPassDetailId(null)}
      />

      {canManage && (
        <TaxiPassFormDialog
          open={formOpen}
          loading={createTaxiPass.isPending}
          onClose={() => setFormOpen(false)}
          onSubmit={(payload) =>
            createTaxiPass.mutate(payload, { onSuccess: () => setFormOpen(false) })
          }
        />
      )}
    </div>
  )
}

// ── Заявки ──────────────────────────────────────────────────────────────────
function RequestsPanel({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation()
  const [filters, setFilters] = useState<AccessRequestsFilters>({ limit: PAGE_LIMIT, offset: 0 })
  const [reviewTarget, setReviewTarget] = useState<ReviewTarget | null>(null)
  const [detailId, setDetailId] = useState<number | null>(null)
  const { data, isLoading, isError } = useAccessRequests(filters)
  const reviewRequest = useReviewRequest()
  const detailRow = data?.items.find((r) => r.id === detailId) ?? null

  const rowActions = canManage
    ? {
        onApprove: (r: ReviewTarget['request']) =>
          setReviewTarget({ request: r, action: 'approve' as const }),
        onReject: (r: ReviewTarget['request']) =>
          setReviewTarget({ request: r, action: 'reject' as const }),
      }
    : undefined

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
          <RequestsTable
            requests={data?.items ?? []}
            actions={rowActions}
            onSelect={(r) => setDetailId(r.id)}
          />
          <AccessPagination
            total={data?.total ?? 0}
            limit={filters.limit ?? PAGE_LIMIT}
            offset={filters.offset ?? 0}
            onOffsetChange={(offset) => setFilters((p) => ({ ...p, offset }))}
          />
        </>
      )}

      <RequestDetailDialog
        requestId={detailId}
        onClose={() => setDetailId(null)}
        onApprove={
          canManage && detailRow
            ? () => {
                setReviewTarget({ request: detailRow, action: 'approve' })
                setDetailId(null)
              }
            : undefined
        }
        onReject={
          canManage && detailRow
            ? () => {
                setReviewTarget({ request: detailRow, action: 'reject' })
                setDetailId(null)
              }
            : undefined
        }
      />

      {canManage && (
        <RequestReviewDialog
          target={reviewTarget}
          loading={reviewRequest.isPending}
          onClose={() => setReviewTarget(null)}
          onSubmit={({ action, comment, zoneIds }) => {
            if (!reviewTarget) return
            reviewRequest.mutate(
              { requestId: reviewTarget.request.id, payload: { action, comment, zone_ids: zoneIds } },
              { onSuccess: () => setReviewTarget(null) },
            )
          }}
        />
      )}
    </div>
  )
}

export default function AccessDatabasePage() {
  const { t } = useTranslation()
  usePageTitle(t('accessControl.database.title'))
  const [tab, setTab] = useState<Tab>('vehicles')
  const canManage = useHasAnyRole(ACCESS_MANAGER_ROLES)

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

      {tab === 'vehicles' && <VehiclesPanel canManage={canManage} />}
      {tab === 'passes' && <PassesPanel canManage={canManage} />}
      {tab === 'requests' && <RequestsPanel canManage={canManage} />}
    </div>
  )
}
