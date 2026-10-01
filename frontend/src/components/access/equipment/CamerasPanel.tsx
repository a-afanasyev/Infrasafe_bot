import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import EquipmentTable, { type EquipmentColumn } from '../EquipmentTable'
import EquipmentFormDialog, { type FormField } from '../EquipmentFormDialog'
import ConfirmDeactivateDialog from '../ConfirmDeactivateDialog'
import { AccessStatusBadge } from '../AccessBadges'
import { useAccessCameras, useCreateCamera, useUpdateCamera } from '../../../hooks/useAccessEquipment'
import type { GateRow, CameraRow, CreateCameraPayload } from '../../../types/access'
import PanelShell from './PanelShell'
import { dash } from './equipmentFormat'

// ── Камеры ──────────────────────────────────────────────────────────────────
export default function CamerasPanel({ gates }: { gates: GateRow[] }) {
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

  const fields: FormField<CreateCameraPayload>[] = [
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
            { id: deactivate.id, payload: { code: deactivate.code, gate_id: deactivate.gate_id, direction: deactivate.direction, is_active: false } },
            { onSuccess: () => setDeactivate(null) },
          )
        }}
      />
    </PanelShell>
  )
}
