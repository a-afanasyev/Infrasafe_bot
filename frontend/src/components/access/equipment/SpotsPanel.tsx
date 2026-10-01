import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import EquipmentTable, { type EquipmentColumn } from '../EquipmentTable'
import EquipmentFormDialog, { type FormField } from '../EquipmentFormDialog'
import ConfirmDeactivateDialog from '../ConfirmDeactivateDialog'
import { AccessStatusBadge } from '../AccessBadges'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useAccessSpots, useCreateSpot, useUpdateSpot } from '../../../hooks/useParkingAdmin'
import type { ZoneRow, SpotRow, CreateSpotPayload } from '../../../types/access'
import PanelShell from './PanelShell'

// ── Места (parking_spots) ─────────────────────────────────────────────────────
export default function SpotsPanel({ canManage, zones }: { canManage: boolean; zones: ZoneRow[] }) {
  const { t } = useTranslation()
  const [zoneFilter, setZoneFilter] = useState('')
  const filters = zoneFilter ? { zone_id: Number(zoneFilter) } : undefined
  const { data, isLoading, isError } = useAccessSpots(filters)
  const create = useCreateSpot()
  const update = useUpdateSpot()

  const [formOpen, setFormOpen] = useState(false)
  const [edit, setEdit] = useState<SpotRow | null>(null)
  const [deactivate, setDeactivate] = useState<SpotRow | null>(null)

  const rows = data?.items ?? []
  const zoneLabel = (id: number) => {
    const z = zones.find((z) => z.id === id)
    return z ? `${z.code} — ${z.name}` : `#${id}`
  }
  const zoneOptions = zones.map((z) => ({ value: String(z.id), label: `${z.code} — ${z.name}` }))
  const statusOptions = (['active', 'inactive', 'archived'] as const).map((s) => ({
    value: s,
    label: t(`accessControl.status.${s}`),
  }))

  const fields: FormField<CreateSpotPayload>[] = [
    { name: 'zone_id', type: 'numberSelect', label: t('accessControl.equipment.fields.zone'), required: true, options: zoneOptions },
    { name: 'code', type: 'text', label: t('accessControl.equipment.fields.code'), required: true },
    { name: 'status', type: 'select', label: t('accessControl.columns.status'), required: true, options: statusOptions, editOnly: true },
  ]

  const columns: EquipmentColumn<SpotRow>[] = [
    { key: 'code', label: t('accessControl.equipment.fields.code'), render: (s) => <span className="font-mono font-semibold">{s.code}</span> },
    { key: 'zone', label: t('accessControl.equipment.fields.zone'), render: (s) => zoneLabel(s.zone_id) },
    { key: 'status', label: t('accessControl.columns.status'), render: (s) => <AccessStatusBadge status={s.status} /> },
  ]

  return (
    <PanelShell
      canManage={canManage}
      addLabel={t('accessControl.parking.addSpot')}
      onAdd={() => { setEdit(null); setFormOpen(true) }}
      isLoading={isLoading}
      isError={isError}
    >
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="spot-zone-filter">{t('accessControl.parking.filters.zone')}</Label>
          <Select
            id="spot-zone-filter"
            value={zoneFilter}
            onChange={(e) => setZoneFilter(e.target.value)}
            className="w-[220px]"
          >
            <option value="">{t('accessControl.parking.filters.allZones')}</option>
            {zoneOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
        </div>
      </div>

      <EquipmentTable
        rows={rows}
        columns={columns}
        emptyIcon="🅿️"
        emptyText={t('accessControl.parking.empty.spots')}
        onEdit={canManage ? (s) => { setEdit(s); setFormOpen(true) } : undefined}
        onDeactivate={canManage ? setDeactivate : undefined}
      />

      {canManage && (
        <>
          <EquipmentFormDialog
            open={formOpen}
            title={edit ? t('accessControl.parking.spotForm.editTitle') : t('accessControl.parking.spotForm.createTitle')}
            fields={fields}
            initial={edit as Record<string, unknown> | null}
            loading={edit ? update.isPending : create.isPending}
            onClose={() => setFormOpen(false)}
            onSubmit={(payload) => {
              if (edit) {
                // PATCH /admin/spots/{id} принимает только code/status.
                update.mutate(
                  { id: edit.id, payload: { code: payload.code as string, status: payload.status as SpotRow['status'] } },
                  { onSuccess: () => setFormOpen(false) },
                )
              } else {
                create.mutate(payload, { onSuccess: () => setFormOpen(false) })
              }
            }}
          />
          <ConfirmDeactivateDialog
            open={deactivate !== null}
            label={deactivate?.code ?? ''}
            loading={update.isPending}
            onClose={() => setDeactivate(null)}
            onConfirm={() => {
              if (!deactivate) return
              update.mutate(
                { id: deactivate.id, payload: { status: 'inactive' } },
                { onSuccess: () => setDeactivate(null) },
              )
            }}
          />
        </>
      )}
    </PanelShell>
  )
}
