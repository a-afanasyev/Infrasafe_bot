import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import EquipmentTable, { type EquipmentColumn } from '../EquipmentTable'
import EquipmentFormDialog, { type FormField } from '../EquipmentFormDialog'
import ConfirmDeactivateDialog from '../ConfirmDeactivateDialog'
import ControllerKeyDialog from '../ControllerKeyDialog'
import ControllerTestDialog from '../ControllerTestDialog'
import { AccessStatusBadge } from '../AccessBadges'
import { Button } from '@/components/ui/button'
import {
  useAccessControllers,
  useCreateController,
  useUpdateController,
  useRotateControllerKey,
} from '../../../hooks/useAccessEquipment'
import type { ZoneRow, GateRow, ControllerRow, CreateControllerPayload } from '../../../types/access'
import PanelShell from './PanelShell'
import { dash } from './equipmentFormat'

// ── Контроллеры ───────────────────────────────────────────────────────────────
export default function ControllersPanel({ zones, gates }: { zones: ZoneRow[]; gates: GateRow[] }) {
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

  const fields: FormField<CreateControllerPayload>[] = [
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
            create.mutate(payload, {
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
