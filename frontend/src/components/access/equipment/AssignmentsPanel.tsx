import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import EquipmentTable, { type EquipmentColumn } from '../EquipmentTable'
import ConfirmDeactivateDialog from '../ConfirmDeactivateDialog'
import SpotAssignmentFormDialog, { ExtendAssignmentDialog } from '../SpotAssignmentFormDialog'
import FreePlaceDialog from '../FreePlaceDialog'
import { AccessStatusBadge } from '../AccessBadges'
import { formatAddress } from '../../../utils/accessMeta'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import {
  useAccessSpots,
  useAccessSpotAssignments,
  useCreateSpotAssignment,
  useUpdateSpotAssignment,
} from '../../../hooks/useParkingAdmin'
import type { ZoneRow, SpotRow, AssignmentRow } from '../../../types/access'
import PanelShell from './PanelShell'
import { fmtDate } from './equipmentFormat'

// ── Закрепления (spot_assignments) ────────────────────────────────────────────
export default function AssignmentsPanel({ canManage, zones }: { canManage: boolean; zones: ZoneRow[] }) {
  const { t } = useTranslation()
  // Все места — для select закрепления, фильтра и подписи строк.
  const spotsQuery = useAccessSpots()
  const spots = spotsQuery.data?.items ?? []

  const [spotFilter, setSpotFilter] = useState('')
  const [apartmentFilter, setApartmentFilter] = useState('')
  const apartmentNum = Number(apartmentFilter)
  const filters = {
    ...(spotFilter ? { spot_id: Number(spotFilter) } : {}),
    ...(apartmentFilter.trim() && Number.isFinite(apartmentNum) ? { apartment_id: apartmentNum } : {}),
  }
  const { data, isLoading, isError } = useAccessSpotAssignments(filters)
  const create = useCreateSpotAssignment()
  const update = useUpdateSpotAssignment()

  const [formOpen, setFormOpen] = useState(false)
  const [revoke, setRevoke] = useState<AssignmentRow | null>(null)
  const [extend, setExtend] = useState<AssignmentRow | null>(null)
  const [freePlace, setFreePlace] = useState<AssignmentRow | null>(null)

  const rows = data?.items ?? []
  const zoneCode = (id: number) => zones.find((z) => z.id === id)?.code ?? `#${id}`
  const spotById = (id: number) => spots.find((s) => s.id === id)
  const spotLabel = (s: SpotRow) => `${zoneCode(s.zone_id)} · ${s.code}`
  const spotCell = (id: number) => {
    const s = spotById(id)
    return s ? spotLabel(s) : `#${id}`
  }
  const spotOptions = spots.map((s) => ({ value: String(s.id), label: spotLabel(s) }))

  const columns: EquipmentColumn<AssignmentRow>[] = [
    { key: 'spot', label: t('accessControl.parking.fields.spot'), render: (a) => <span className="font-mono">{spotCell(a.spot_id)}</span> },
    { key: 'apartment', label: t('accessControl.parking.fields.owner'), render: (a) => formatAddress(a.address, t) },
    { key: 'ownership', label: t('accessControl.parking.fields.ownershipType'), render: (a) => t(`accessControl.parking.ownershipType.${a.ownership_type}`, { defaultValue: a.ownership_type }) },
    {
      key: 'enforce',
      label: t('accessControl.parking.fields.enforceLimit'),
      render: (a) => (
        <input
          type="checkbox"
          role="switch"
          aria-label={t('accessControl.parking.fields.enforceLimit')}
          title={t('accessControl.parking.enforceLimitHint')}
          checked={a.enforce_limit}
          disabled={!canManage || update.isPending}
          onChange={() => update.mutate({ id: a.id, payload: { enforce_limit: !a.enforce_limit } })}
          className="h-4 w-4 cursor-pointer accent-emerald-500"
        />
      ),
    },
    {
      key: 'occupied',
      label: t('accessControl.parking.fields.occupied'),
      render: (a) => (
        <span className="font-mono">
          {t('accessControl.parking.fields.occupiedOf', { occupied: a.occupied, spots: a.spots })}
        </span>
      ),
    },
    { key: 'from', label: t('accessControl.parking.fields.validFrom'), render: (a) => fmtDate(a.valid_from) },
    { key: 'until', label: t('accessControl.parking.fields.validUntil'), render: (a) => fmtDate(a.valid_until) },
    { key: 'status', label: t('accessControl.columns.status'), render: (a) => <AccessStatusBadge status={a.status} /> },
  ]

  return (
    <PanelShell
      canManage={canManage}
      addLabel={t('accessControl.parking.addAssignment')}
      onAdd={() => setFormOpen(true)}
      isLoading={isLoading}
      isError={isError}
    >
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="asg-spot-filter">{t('accessControl.parking.filters.spot')}</Label>
          <Select
            id="asg-spot-filter"
            value={spotFilter}
            onChange={(e) => setSpotFilter(e.target.value)}
            className="w-[220px]"
          >
            <option value="">{t('accessControl.parking.filters.allSpots')}</option>
            {spotOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="asg-apt-filter">{t('accessControl.parking.filters.apartmentId')}</Label>
          <Input
            id="asg-apt-filter"
            type="number"
            value={apartmentFilter}
            onChange={(e) => setApartmentFilter(e.target.value)}
            className="w-[140px]"
          />
        </div>
      </div>

      <EquipmentTable
        rows={rows}
        columns={columns}
        emptyIcon="🔗"
        emptyText={t('accessControl.parking.empty.assignments')}
        extraActions={
          canManage
            ? (a) => (
                <>
                  <Button size="sm" variant="outline" onClick={() => setExtend(a)}>
                    {t('accessControl.parking.actions.extend')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setFreePlace(a)}>
                    {t('accessControl.parking.actions.freePlace')}
                  </Button>
                  {a.status === 'active' && (
                    <Button size="sm" variant="destructive" onClick={() => setRevoke(a)}>
                      {t('accessControl.parking.actions.revoke')}
                    </Button>
                  )}
                </>
              )
            : undefined
        }
      />

      <FreePlaceDialog
        apartmentId={freePlace?.apartment_id ?? null}
        zoneId={freePlace ? (spotById(freePlace.spot_id)?.zone_id ?? null) : null}
        onClose={() => setFreePlace(null)}
      />

      {canManage && (
        <>
          <SpotAssignmentFormDialog
            open={formOpen}
            spots={spots}
            spotLabel={spotLabel}
            loading={create.isPending}
            onClose={() => setFormOpen(false)}
            onSubmit={(payload) => create.mutate(payload, { onSuccess: () => setFormOpen(false) })}
          />
          <ExtendAssignmentDialog
            open={extend !== null}
            loading={update.isPending}
            onClose={() => setExtend(null)}
            onSubmit={(payload) => {
              if (!extend) return
              update.mutate({ id: extend.id, payload }, { onSuccess: () => setExtend(null) })
            }}
          />
          <ConfirmDeactivateDialog
            open={revoke !== null}
            label={revoke ? spotCell(revoke.spot_id) : ''}
            loading={update.isPending}
            onClose={() => setRevoke(null)}
            onConfirm={() => {
              if (!revoke) return
              update.mutate(
                { id: revoke.id, payload: { status: 'revoked' } },
                { onSuccess: () => setRevoke(null) },
              )
            }}
            title={t('accessControl.parking.revokeTitle')}
            message={t('accessControl.parking.revokeConfirm', { spot: spotCell(revoke?.spot_id ?? 0) })}
            confirmLabel={t('accessControl.parking.actions.revoke')}
          />
        </>
      )}
    </PanelShell>
  )
}
