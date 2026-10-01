import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import EquipmentTable, { type EquipmentColumn } from '../EquipmentTable'
import ZoneFormDialog from '../ZoneFormDialog'
import ConfirmDeactivateDialog from '../ConfirmDeactivateDialog'
import { AccessStatusBadge, ParkingTypeBadge } from '../AccessBadges'
import { useAccessZones, useCreateZone, useUpdateZone, useUpdateZoneYards } from '../../../hooks/useAccessEquipment'
import { useZoneOccupancy } from '../../../hooks/useParkingAdmin'
import type { ZoneRow } from '../../../types/access'
import PanelShell from './PanelShell'
import { dash } from './equipmentFormat'

// Ячейка занятости shared-зоны (occupancy/capacity). Для assigned-зон — прочерк.
function ZoneOccupancyCell({ zone }: { zone: ZoneRow }) {
  const isShared = zone.parking_type === 'shared'
  const { data, isLoading } = useZoneOccupancy(zone.id, isShared)
  if (!isShared) return <span className="text-text-muted">—</span>
  if (isLoading) return <span className="text-text-muted">…</span>
  const cap = data?.capacity ?? zone.capacity ?? null
  if (!data) return <span className="text-text-muted">—</span>
  return (
    <span className="font-mono">
      {data.occupancy}
      {cap != null ? ` / ${cap}` : ''}
    </span>
  )
}

// ── Зоны ──────────────────────────────────────────────────────────────────────
export default function ZonesPanel({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessZones()
  const createZone = useCreateZone()
  const updateZone = useUpdateZone()
  const updateYards = useUpdateZoneYards()

  const [formOpen, setFormOpen] = useState(false)
  const [editZone, setEditZone] = useState<ZoneRow | null>(null)
  const [deactivate, setDeactivate] = useState<ZoneRow | null>(null)

  const rows = data?.items ?? []
  // Актуальные yard_ids редактируемой зоны (после мутаций — из свежего списка).
  const editYardIds = editZone ? (rows.find((z) => z.id === editZone.id)?.yard_ids ?? editZone.yard_ids ?? []) : []

  const columns: EquipmentColumn<ZoneRow>[] = [
    { key: 'code', label: t('accessControl.equipment.fields.code'), render: (z) => <span className="font-mono font-semibold">{z.code}</span> },
    { key: 'name', label: t('accessControl.equipment.fields.name'), render: (z) => z.name },
    { key: 'parking_type', label: t('accessControl.parking.fields.parkingType'), render: (z) => <ParkingTypeBadge type={z.parking_type ?? 'assigned'} /> },
    { key: 'occupancy', label: t('accessControl.parking.fields.occupancy'), render: (z) => <ZoneOccupancyCell zone={z} /> },
    { key: 'offline', label: t('accessControl.equipment.fields.offlineMode'), render: (z) => t(`accessControl.equipment.offlineMode.${z.offline_mode}`, { defaultValue: z.offline_mode }) },
    { key: 'max', label: t('accessControl.parking.fields.maxPermanentVehicles'), render: (z) => dash(z.max_permanent_vehicles_per_apartment) },
    { key: 'yards', label: t('accessControl.equipment.zoneForm.yardsLabel'), render: (z) => (z.yard_ids && z.yard_ids.length ? z.yard_ids.map((y) => `#${y}`).join(', ') : '—') },
    { key: 'status', label: t('accessControl.columns.status'), render: (z) => <AccessStatusBadge status={z.is_active ? 'active' : 'archived'} /> },
  ]

  function openCreate() {
    setEditZone(null)
    setFormOpen(true)
  }
  function openEdit(z: ZoneRow) {
    setEditZone(z)
    setFormOpen(true)
  }

  return (
    <PanelShell
      canManage={canManage}
      addLabel={t('accessControl.equipment.addZone')}
      onAdd={openCreate}
      isLoading={isLoading}
      isError={isError}
    >
      <EquipmentTable
        rows={rows}
        columns={columns}
        emptyIcon="🗺️"
        emptyText={t('accessControl.equipment.empty.zones')}
        onEdit={canManage ? openEdit : undefined}
        onDeactivate={canManage ? setDeactivate : undefined}
      />

      {canManage && (
        <>
          <ZoneFormDialog
            open={formOpen}
            zone={editZone}
            yardIds={editYardIds}
            loading={editZone ? updateZone.isPending : createZone.isPending}
            yardsLoading={updateYards.isPending}
            onClose={() => setFormOpen(false)}
            onSubmit={(payload) => {
              if (editZone) {
                updateZone.mutate({ id: editZone.id, payload }, { onSuccess: () => setFormOpen(false) })
              } else {
                createZone.mutate(payload, { onSuccess: () => setFormOpen(false) })
              }
            }}
            onAddYard={(yardId) => editZone && updateYards.mutate({ id: editZone.id, payload: { add: [yardId] } })}
            onRemoveYard={(yardId) => editZone && updateYards.mutate({ id: editZone.id, payload: { remove: [yardId] } })}
          />
          <ConfirmDeactivateDialog
            open={deactivate !== null}
            label={deactivate?.code ?? ''}
            loading={updateZone.isPending}
            onClose={() => setDeactivate(null)}
            onConfirm={() => {
              if (!deactivate) return
              updateZone.mutate(
                {
                  id: deactivate.id,
                  payload: { code: deactivate.code, name: deactivate.name, offline_mode: deactivate.offline_mode, is_active: false },
                },
                { onSuccess: () => setDeactivate(null) },
              )
            }}
          />
        </>
      )}
    </PanelShell>
  )
}
