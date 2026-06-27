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
import { AccessStatusBadge } from '../../components/access/AccessBadges'
import LoadingSpinner from '../../components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
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
import type {
  ZoneRow,
  GateRow,
  CameraRow,
  BarrierRow,
  ControllerRow,
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
type Tab = 'zones' | 'gates' | 'cameras' | 'barriers' | 'controllers'

function dash(v: unknown): React.ReactNode {
  return v === null || v === undefined || v === '' ? '—' : String(v)
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
      {activeTab === 'gates' && <GatesPanel canManage zones={zones} />}
      {activeTab === 'cameras' && isAdmin && <CamerasPanel gates={gates} />}
      {activeTab === 'barriers' && isAdmin && <BarriersPanel gates={gates} />}
      {activeTab === 'controllers' && isAdmin && <ControllersPanel zones={zones} gates={gates} />}
    </div>
  )
}
