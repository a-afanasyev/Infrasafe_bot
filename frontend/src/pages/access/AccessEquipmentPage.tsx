import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Cpu, Plus } from 'lucide-react'
import { usePageTitle } from '../../hooks/usePageTitle'
import AccessTabBar from '../../components/access/AccessTabBar'
import EquipmentTable, { type EquipmentColumn } from '../../components/access/EquipmentTable'
import EquipmentFormDialog, { type FormField } from '../../components/access/EquipmentFormDialog'
import ZoneFormDialog from '../../components/access/ZoneFormDialog'
import ConfirmDeactivateDialog from '../../components/access/ConfirmDeactivateDialog'
import ControllerKeyDialog from '../../components/access/ControllerKeyDialog'
import ControllerTestDialog from '../../components/access/ControllerTestDialog'
import SpotAssignmentFormDialog, {
  ExtendAssignmentDialog,
} from '../../components/access/SpotAssignmentFormDialog'
import FreePlaceDialog from '../../components/access/FreePlaceDialog'
import { AccessStatusBadge, ParkingTypeBadge } from '../../components/access/AccessBadges'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { useHasRole } from '../../hooks/useHasRole'
import {
  useAccessZones,
  useCreateZone,
  useUpdateZone,
  useUpdateZoneYards,
  useAccessGates,
  useCreateGate,
  useUpdateGate,
  useAccessCameras,
  useCreateCamera,
  useUpdateCamera,
  useAccessBarriers,
  useCreateBarrier,
  useUpdateBarrier,
  useAccessControllers,
  useCreateController,
  useUpdateController,
  useRotateControllerKey,
} from '../../hooks/useAccessEquipment'
import {
  useAccessSpots,
  useCreateSpot,
  useUpdateSpot,
  useAccessSpotAssignments,
  useCreateSpotAssignment,
  useUpdateSpotAssignment,
  useZoneOccupancy,
} from '../../hooks/useParkingAdmin'
import type {
  ZoneRow,
  GateRow,
  CameraRow,
  BarrierRow,
  ControllerRow,
  SpotRow,
  AssignmentRow,
} from '../../types/access'

/**
 * Экран «Оборудование» (управление точками въезда). Табы фильтруются по роли:
 *  - manager: Зоны, Въезды;
 *  - system_admin: + Камеры, Шлагбаумы, Контроллеры (бэкенд отдаёт их GET только
 *    system_admin; manager получил бы 403, поэтому эти табы для него скрыты).
 *
 * Route уже закрыт ACCESS_MANAGER_ROLES (App.tsx) — здесь дополнительный гейтинг
 * табов/действий по system_admin (useHasRole).
 */
type Tab = 'zones' | 'spots' | 'assignments' | 'gates' | 'cameras' | 'barriers' | 'controllers'

function dash(v: unknown): React.ReactNode {
  return v === null || v === undefined || v === '' ? '—' : String(v)
}

/** Дата ISO → локальная короткая строка (или прочерк). */
function fmtDate(v: string | null): React.ReactNode {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString()
}

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
function ZonesPanel({ canManage }: { canManage: boolean }) {
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
    { key: 'max', label: t('accessControl.equipment.fields.maxPermanent'), render: (z) => dash(z.max_permanent_per_apartment) },
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

// ── Места (parking_spots) ─────────────────────────────────────────────────────
function SpotsPanel({ canManage, zones }: { canManage: boolean; zones: ZoneRow[] }) {
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

  const fields: FormField[] = [
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
                create.mutate(payload as never, { onSuccess: () => setFormOpen(false) })
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

// ── Закрепления (spot_assignments) ────────────────────────────────────────────
function AssignmentsPanel({ canManage, zones }: { canManage: boolean; zones: ZoneRow[] }) {
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
    { key: 'apartment', label: t('accessControl.parking.fields.apartmentId'), render: (a) => `#${a.apartment_id}` },
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

// ── Въезды ──────────────────────────────────────────────────────────────────
function GatesPanel({ canManage, zones }: { canManage: boolean; zones: ZoneRow[] }) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessGates()
  const createGate = useCreateGate()
  const updateGate = useUpdateGate()

  const [formOpen, setFormOpen] = useState(false)
  const [edit, setEdit] = useState<GateRow | null>(null)
  const [deactivate, setDeactivate] = useState<GateRow | null>(null)

  const rows = data?.items ?? []
  const zoneLabel = (id: number) => {
    const z = zones.find((z) => z.id === id)
    return z ? `${z.code} — ${z.name}` : `#${id}`
  }
  const zoneOptions = zones.map((z) => ({ value: String(z.id), label: `${z.code} — ${z.name}` }))
  const directionOptions = (['entry', 'exit'] as const).map((d) => ({ value: d, label: t(`accessControl.direction.${d}`) }))

  const fields: FormField[] = [
    { name: 'code', type: 'text', label: t('accessControl.equipment.fields.code'), required: true },
    { name: 'zone_id', type: 'numberSelect', label: t('accessControl.equipment.fields.zone'), required: true, options: zoneOptions },
    { name: 'direction', type: 'select', label: t('accessControl.columns.direction'), required: true, options: directionOptions },
    { name: 'name', type: 'text', label: t('accessControl.equipment.fields.name') },
    { name: 'is_active', type: 'checkbox', label: t('accessControl.equipment.fields.isActive'), editOnly: true },
  ]

  const columns: EquipmentColumn<GateRow>[] = [
    { key: 'code', label: t('accessControl.equipment.fields.code'), render: (g) => <span className="font-mono font-semibold">{g.code}</span> },
    { key: 'zone', label: t('accessControl.equipment.fields.zone'), render: (g) => zoneLabel(g.zone_id) },
    { key: 'direction', label: t('accessControl.columns.direction'), render: (g) => t(`accessControl.direction.${g.direction}`, { defaultValue: g.direction }) },
    { key: 'name', label: t('accessControl.equipment.fields.name'), render: (g) => dash(g.name) },
    { key: 'status', label: t('accessControl.columns.status'), render: (g) => <AccessStatusBadge status={g.is_active ? 'active' : 'archived'} /> },
  ]

  return (
    <PanelShell
      canManage={canManage}
      addLabel={t('accessControl.equipment.addGate')}
      onAdd={() => { setEdit(null); setFormOpen(true) }}
      isLoading={isLoading}
      isError={isError}
    >
      <EquipmentTable
        rows={rows}
        columns={columns}
        emptyIcon="🚧"
        emptyText={t('accessControl.equipment.empty.gates')}
        onEdit={canManage ? (g) => { setEdit(g); setFormOpen(true) } : undefined}
        onDeactivate={canManage ? setDeactivate : undefined}
      />

      {canManage && (
        <>
          <EquipmentFormDialog
            open={formOpen}
            title={edit ? t('accessControl.equipment.gateForm.editTitle') : t('accessControl.equipment.gateForm.createTitle')}
            fields={fields}
            initial={edit as Record<string, unknown> | null}
            loading={edit ? updateGate.isPending : createGate.isPending}
            onClose={() => setFormOpen(false)}
            onSubmit={(payload) => {
              if (edit) {
                updateGate.mutate({ id: edit.id, payload }, { onSuccess: () => setFormOpen(false) })
              } else {
                createGate.mutate(payload as never, { onSuccess: () => setFormOpen(false) })
              }
            }}
          />
          <ConfirmDeactivateDialog
            open={deactivate !== null}
            label={deactivate?.code ?? ''}
            loading={updateGate.isPending}
            onClose={() => setDeactivate(null)}
            onConfirm={() => {
              if (!deactivate) return
              updateGate.mutate(
                { id: deactivate.id, payload: { code: deactivate.code, zone_id: deactivate.zone_id, direction: deactivate.direction, is_active: false } },
                { onSuccess: () => setDeactivate(null) },
              )
            }}
          />
        </>
      )}
    </PanelShell>
  )
}

// ── Камеры ──────────────────────────────────────────────────────────────────
function CamerasPanel({ gates }: { gates: GateRow[] }) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessCameras()
  const create = useCreateCamera()
  const update = useUpdateCamera()

  const [formOpen, setFormOpen] = useState(false)
  const [edit, setEdit] = useState<CameraRow | null>(null)
  const [deactivate, setDeactivate] = useState<CameraRow | null>(null)

  const rows = data?.items ?? []
  const gateLabel = (id: number) => gates.find((g) => g.id === id)?.code ?? `#${id}`
  const gateOptions = gates.map((g) => ({ value: String(g.id), label: g.code }))
  const directionOptions = (['entry', 'exit'] as const).map((d) => ({ value: d, label: t(`accessControl.direction.${d}`) }))

  const fields: FormField[] = [
    { name: 'code', type: 'text', label: t('accessControl.equipment.fields.code'), required: true },
    { name: 'gate_id', type: 'numberSelect', label: t('accessControl.equipment.fields.gate'), required: true, options: gateOptions },
    { name: 'direction', type: 'select', label: t('accessControl.columns.direction'), required: true, options: directionOptions },
    { name: 'name', type: 'text', label: t('accessControl.equipment.fields.name') },
    { name: 'vendor', type: 'text', label: t('accessControl.equipment.fields.vendor') },
    { name: 'model', type: 'text', label: t('accessControl.equipment.fields.model') },
    { name: 'attributes', type: 'json', label: t('accessControl.equipment.fields.attributes'), placeholder: '{ "fps": 25 }' },
    { name: 'is_active', type: 'checkbox', label: t('accessControl.equipment.fields.isActive'), editOnly: true },
  ]

  const columns: EquipmentColumn<CameraRow>[] = [
    { key: 'code', label: t('accessControl.equipment.fields.code'), render: (c) => <span className="font-mono font-semibold">{c.code}</span> },
    { key: 'gate', label: t('accessControl.equipment.fields.gate'), render: (c) => gateLabel(c.gate_id) },
    { key: 'direction', label: t('accessControl.columns.direction'), render: (c) => t(`accessControl.direction.${c.direction}`, { defaultValue: c.direction }) },
    { key: 'vendor', label: t('accessControl.equipment.fields.vendor'), render: (c) => dash([c.vendor, c.model].filter(Boolean).join(' ')) },
    { key: 'status', label: t('accessControl.columns.status'), render: (c) => <AccessStatusBadge status={c.is_active ? 'active' : 'archived'} /> },
  ]

  return (
    <PanelShell
      canManage
      addLabel={t('accessControl.equipment.addCamera')}
      onAdd={() => { setEdit(null); setFormOpen(true) }}
      isLoading={isLoading}
      isError={isError}
    >
      <EquipmentTable
        rows={rows}
        columns={columns}
        emptyIcon="📷"
        emptyText={t('accessControl.equipment.empty.cameras')}
        onEdit={(c) => { setEdit(c); setFormOpen(true) }}
        onDeactivate={setDeactivate}
      />
      <EquipmentFormDialog
        open={formOpen}
        title={edit ? t('accessControl.equipment.cameraForm.editTitle') : t('accessControl.equipment.cameraForm.createTitle')}
        fields={fields}
        initial={edit as Record<string, unknown> | null}
        loading={edit ? update.isPending : create.isPending}
        onClose={() => setFormOpen(false)}
        onSubmit={(payload) => {
          if (edit) {
            update.mutate({ id: edit.id, payload }, { onSuccess: () => setFormOpen(false) })
          } else {
            create.mutate(payload as never, { onSuccess: () => setFormOpen(false) })
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
            { id: deactivate.id, payload: { code: deactivate.code, gate_id: deactivate.gate_id, direction: deactivate.direction, is_active: false } },
            { onSuccess: () => setDeactivate(null) },
          )
        }}
      />
    </PanelShell>
  )
}

// ── Шлагбаумы ─────────────────────────────────────────────────────────────────
function BarriersPanel({ gates }: { gates: GateRow[] }) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessBarriers()
  const create = useCreateBarrier()
  const update = useUpdateBarrier()

  const [formOpen, setFormOpen] = useState(false)
  const [edit, setEdit] = useState<BarrierRow | null>(null)
  const [deactivate, setDeactivate] = useState<BarrierRow | null>(null)

  const rows = data?.items ?? []
  const gateLabel = (id: number) => gates.find((g) => g.id === id)?.code ?? `#${id}`
  const gateOptions = gates.map((g) => ({ value: String(g.id), label: g.code }))

  const fields: FormField[] = [
    { name: 'code', type: 'text', label: t('accessControl.equipment.fields.code'), required: true },
    { name: 'gate_id', type: 'numberSelect', label: t('accessControl.equipment.fields.gate'), required: true, options: gateOptions },
    { name: 'name', type: 'text', label: t('accessControl.equipment.fields.name') },
    { name: 'relay_type', type: 'text', label: t('accessControl.equipment.fields.relayType') },
    { name: 'relay_channel', type: 'number', label: t('accessControl.equipment.fields.relayChannel') },
    { name: 'config', type: 'json', label: t('accessControl.equipment.fields.config'), placeholder: '{ "pulse_ms": 500 }' },
    { name: 'is_active', type: 'checkbox', label: t('accessControl.equipment.fields.isActive'), editOnly: true },
  ]

  const columns: EquipmentColumn<BarrierRow>[] = [
    { key: 'code', label: t('accessControl.equipment.fields.code'), render: (b) => <span className="font-mono font-semibold">{b.code}</span> },
    { key: 'gate', label: t('accessControl.equipment.fields.gate'), render: (b) => gateLabel(b.gate_id) },
    { key: 'relay', label: t('accessControl.equipment.fields.relayType'), render: (b) => dash([b.relay_type, b.relay_channel != null ? `#${b.relay_channel}` : ''].filter(Boolean).join(' ')) },
    { key: 'status', label: t('accessControl.columns.status'), render: (b) => <AccessStatusBadge status={b.is_active ? 'active' : 'archived'} /> },
  ]

  return (
    <PanelShell
      canManage
      addLabel={t('accessControl.equipment.addBarrier')}
      onAdd={() => { setEdit(null); setFormOpen(true) }}
      isLoading={isLoading}
      isError={isError}
    >
      <EquipmentTable
        rows={rows}
        columns={columns}
        emptyIcon="⛔"
        emptyText={t('accessControl.equipment.empty.barriers')}
        onEdit={(b) => { setEdit(b); setFormOpen(true) }}
        onDeactivate={setDeactivate}
      />
      <EquipmentFormDialog
        open={formOpen}
        title={edit ? t('accessControl.equipment.barrierForm.editTitle') : t('accessControl.equipment.barrierForm.createTitle')}
        fields={fields}
        initial={edit as Record<string, unknown> | null}
        loading={edit ? update.isPending : create.isPending}
        onClose={() => setFormOpen(false)}
        onSubmit={(payload) => {
          if (edit) {
            update.mutate({ id: edit.id, payload }, { onSuccess: () => setFormOpen(false) })
          } else {
            create.mutate(payload as never, { onSuccess: () => setFormOpen(false) })
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
            { id: deactivate.id, payload: { code: deactivate.code, gate_id: deactivate.gate_id, is_active: false } },
            { onSuccess: () => setDeactivate(null) },
          )
        }}
      />
    </PanelShell>
  )
}

// ── Контроллеры ───────────────────────────────────────────────────────────────
function ControllersPanel({ zones, gates }: { zones: ZoneRow[]; gates: GateRow[] }) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessControllers()
  const create = useCreateController()
  const update = useUpdateController()
  const rotate = useRotateControllerKey()

  const [formOpen, setFormOpen] = useState(false)
  const [edit, setEdit] = useState<ControllerRow | null>(null)
  const [deactivate, setDeactivate] = useState<ControllerRow | null>(null)
  const [rotateTarget, setRotateTarget] = useState<ControllerRow | null>(null)
  const [testTarget, setTestTarget] = useState<ControllerRow | null>(null)
  // Показ api_key РОВНО ОДИН РАЗ (создание/ротация) — модалка ControllerKeyDialog.
  const [keyResult, setKeyResult] = useState<{ uid: string; apiKey: string } | null>(null)

  const rows = data?.items ?? []
  const zoneOptions = zones.map((z) => ({ value: String(z.id), label: `${z.code} — ${z.name}` }))
  const gateOptions = gates.map((g) => ({ value: String(g.id), label: g.code }))
  const offlineOptions = (['fail_closed', 'cached_permanent_only'] as const).map((m) => ({
    value: m,
    label: t(`accessControl.equipment.offlineMode.${m}`),
  }))

  const fields: FormField[] = [
    { name: 'controller_uid', type: 'text', label: t('accessControl.equipment.fields.controllerUid'), required: true },
    { name: 'name', type: 'text', label: t('accessControl.equipment.fields.name') },
    { name: 'zone_id', type: 'numberSelect', label: t('accessControl.equipment.fields.zone'), options: zoneOptions },
    { name: 'gate_id', type: 'numberSelect', label: t('accessControl.equipment.fields.gate'), options: gateOptions },
    { name: 'offline_mode', type: 'select', label: t('accessControl.equipment.fields.offlineMode'), options: offlineOptions },
    { name: 'ip_allowlist', type: 'csv', label: t('accessControl.equipment.fields.ipAllowlist'), placeholder: t('accessControl.equipment.fields.ipAllowlistPlaceholder') },
    { name: 'is_active', type: 'checkbox', label: t('accessControl.equipment.fields.isActive'), editOnly: true },
  ]

  const columns: EquipmentColumn<ControllerRow>[] = [
    { key: 'uid', label: t('accessControl.equipment.fields.controllerUid'), render: (c) => <span className="font-mono font-semibold">{c.controller_uid}</span> },
    { key: 'name', label: t('accessControl.equipment.fields.name'), render: (c) => dash(c.name) },
    { key: 'status', label: t('accessControl.columns.status'), render: (c) => <AccessStatusBadge status={c.is_active ? (c.status ?? 'active') : 'archived'} /> },
    { key: 'ip', label: t('accessControl.equipment.fields.ipAllowlist'), render: (c) => (c.ip_allowlist && c.ip_allowlist.length ? c.ip_allowlist.join(', ') : '—') },
  ]

  return (
    <PanelShell
      canManage
      addLabel={t('accessControl.equipment.addController')}
      onAdd={() => { setEdit(null); setFormOpen(true) }}
      isLoading={isLoading}
      isError={isError}
    >
      <EquipmentTable
        rows={rows}
        columns={columns}
        emptyIcon="🎛️"
        emptyText={t('accessControl.equipment.empty.controllers')}
        onEdit={(c) => { setEdit(c); setFormOpen(true) }}
        onDeactivate={setDeactivate}
        extraActions={(c) => (
          <>
            <Button size="sm" variant="outline" onClick={() => setTestTarget(c)}>
              {t('accessControl.equipment.test.action')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setRotateTarget(c)}>
              {t('accessControl.equipment.rotateKey')}
            </Button>
          </>
        )}
      />

      <EquipmentFormDialog
        open={formOpen}
        title={edit ? t('accessControl.equipment.controllerForm.editTitle') : t('accessControl.equipment.controllerForm.createTitle')}
        description={edit ? undefined : t('accessControl.equipment.controllerForm.createDesc')}
        fields={fields}
        initial={edit as Record<string, unknown> | null}
        loading={edit ? update.isPending : create.isPending}
        onClose={() => setFormOpen(false)}
        onSubmit={(payload) => {
          if (edit) {
            update.mutate({ id: edit.id, payload }, { onSuccess: () => setFormOpen(false) })
          } else {
            create.mutate(payload as never, {
              onSuccess: (res) => {
                setFormOpen(false)
                setKeyResult({ uid: res.controller_uid, apiKey: res.api_key })
              },
            })
          }
        }}
      />

      <ConfirmDeactivateDialog
        open={deactivate !== null}
        label={deactivate?.controller_uid ?? ''}
        loading={update.isPending}
        onClose={() => setDeactivate(null)}
        onConfirm={() => {
          if (!deactivate) return
          update.mutate(
            { id: deactivate.id, payload: { is_active: false } },
            { onSuccess: () => setDeactivate(null) },
          )
        }}
      />

      {/* Подтверждение ротации ключа → затем показ нового ключа (один раз). */}
      <ConfirmDeactivateDialog
        open={rotateTarget !== null}
        label={rotateTarget?.controller_uid ?? ''}
        loading={rotate.isPending}
        onClose={() => setRotateTarget(null)}
        onConfirm={() => {
          if (!rotateTarget) return
          rotate.mutate(
            { id: rotateTarget.id },
            {
              onSuccess: (res) => {
                setRotateTarget(null)
                setKeyResult({ uid: res.controller_uid, apiKey: res.api_key })
              },
            },
          )
        }}
        confirmLabel={t('accessControl.equipment.rotateKey')}
        title={t('accessControl.equipment.rotateConfirmTitle')}
        message={t('accessControl.equipment.rotateConfirm', { uid: rotateTarget?.controller_uid ?? '' })}
      />

      <ControllerKeyDialog
        controllerUid={keyResult?.uid ?? null}
        apiKey={keyResult?.apiKey ?? null}
        onClose={() => setKeyResult(null)}
      />

      <ControllerTestDialog
        controller={testTarget}
        zones={zones}
        gates={gates}
        onClose={() => setTestTarget(null)}
      />
    </PanelShell>
  )
}

// ── Общая обёртка панели (кнопка «Добавить» + загрузка/ошибка) ────────────────
function PanelShell({
  canManage,
  addLabel,
  onAdd,
  isLoading,
  isError,
  children,
}: {
  canManage: boolean
  addLabel: string
  onAdd: () => void
  isLoading: boolean
  isError: boolean
  children: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-4">
      {canManage && (
        <div className="flex justify-end">
          <Button onClick={onAdd} className="gap-1.5">
            <Plus size={16} />
            {addLabel}
          </Button>
        </div>
      )}
      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <p className="text-[13px] text-red">{t('common.error')}</p>
      ) : (
        children
      )}
    </div>
  )
}

export default function AccessEquipmentPage() {
  const { t } = useTranslation()
  usePageTitle(t('accessControl.equipment.title'))
  const isAdmin = useHasRole('system_admin')
  const [tab, setTab] = useState<Tab>('zones')

  // Источники для select'ов (зоны/въезды) + таблицы своих табов.
  const zonesQuery = useAccessZones()
  const gatesQuery = useAccessGates()
  const zones = zonesQuery.data?.items ?? []
  const gates = gatesQuery.data?.items ?? []

  const tabs = [
    { key: 'zones', label: t('accessControl.equipment.tabs.zones') },
    { key: 'spots', label: t('accessControl.parking.tabs.spots') },
    { key: 'assignments', label: t('accessControl.parking.tabs.assignments') },
    { key: 'gates', label: t('accessControl.equipment.tabs.gates') },
    ...(isAdmin
      ? [
          { key: 'cameras', label: t('accessControl.equipment.tabs.cameras') },
          { key: 'barriers', label: t('accessControl.equipment.tabs.barriers') },
          { key: 'controllers', label: t('accessControl.equipment.tabs.controllers') },
        ]
      : []),
  ]

  // Защита: если неадмин как-то оказался на admin-табе — вернуть на «Зоны».
  const adminTabs: Tab[] = ['cameras', 'barriers', 'controllers']
  const activeTab: Tab = !isAdmin && adminTabs.includes(tab) ? 'zones' : tab

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-center gap-2.5">
        <Cpu className="text-accent" size={22} />
        <div>
          <h1 className="text-xl font-semibold text-text-primary">{t('accessControl.equipment.title')}</h1>
          <p className="text-[13px] text-text-muted">{t('accessControl.equipment.subtitle')}</p>
        </div>
      </div>

      <AccessTabBar tabs={tabs} active={activeTab} onChange={(k) => setTab(k as Tab)} />

      {activeTab === 'zones' && <ZonesPanel canManage />}
      {activeTab === 'spots' && <SpotsPanel canManage zones={zones} />}
      {activeTab === 'assignments' && <AssignmentsPanel canManage zones={zones} />}
      {activeTab === 'gates' && <GatesPanel canManage zones={zones} />}
      {activeTab === 'cameras' && isAdmin && <CamerasPanel gates={gates} />}
      {activeTab === 'barriers' && isAdmin && <BarriersPanel gates={gates} />}
      {activeTab === 'controllers' && isAdmin && <ControllersPanel zones={zones} gates={gates} />}
    </div>
  )
}
