import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import EquipmentTable, { type EquipmentColumn } from '../EquipmentTable'
import EquipmentFormDialog, { type FormField } from '../EquipmentFormDialog'
import ConfirmDeactivateDialog from '../ConfirmDeactivateDialog'
import { AccessStatusBadge } from '../AccessBadges'
import { useAccessGates, useCreateGate, useUpdateGate } from '../../../hooks/useAccessEquipment'
import type { ZoneRow, GateRow, CreateGatePayload } from '../../../types/access'
import PanelShell from './PanelShell'
import { dash } from './equipmentFormat'

// ── Въезды ──────────────────────────────────────────────────────────────────
export default function GatesPanel({ canManage, zones }: { canManage: boolean; zones: ZoneRow[] }) {
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

  const fields: FormField<CreateGatePayload>[] = [
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
                createGate.mutate(payload, { onSuccess: () => setFormOpen(false) })
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
