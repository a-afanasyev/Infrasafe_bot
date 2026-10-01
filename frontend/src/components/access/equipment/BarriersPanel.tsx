import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import EquipmentTable, { type EquipmentColumn } from '../EquipmentTable'
import EquipmentFormDialog, { type FormField } from '../EquipmentFormDialog'
import ConfirmDeactivateDialog from '../ConfirmDeactivateDialog'
import { AccessStatusBadge } from '../AccessBadges'
import { useAccessBarriers, useCreateBarrier, useUpdateBarrier } from '../../../hooks/useAccessEquipment'
import type { GateRow, BarrierRow, CreateBarrierPayload } from '../../../types/access'
import PanelShell from './PanelShell'
import { dash } from './equipmentFormat'

// ── Шлагбаумы ─────────────────────────────────────────────────────────────────
export default function BarriersPanel({ gates }: { gates: GateRow[] }) {
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

  const fields: FormField<CreateBarrierPayload>[] = [
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
            { id: deactivate.id, payload: { code: deactivate.code, gate_id: deactivate.gate_id, is_active: false } },
            { onSuccess: () => setDeactivate(null) },
          )
        }}
      />
    </PanelShell>
  )
}
