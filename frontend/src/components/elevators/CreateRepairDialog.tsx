import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { DialogShell, Field } from './DialogShell'
import { useOpenReset } from '../../hooks/useOpenReset'
import { URGENCIES } from '../../constants'
import { tUrgency } from '../../i18n/apiMaps'
import { useCreateElevatorRepair } from '../../hooks/useElevators'
import type { ElevatorDetail } from '../../types/elevators'

/**
 * «Создать ремонт» из карточки лифта → POST /api/v2/callcenter/requests с
 * category=elevator, building_id (адрес уровня дома — без него 422),
 * elevator_id, elevator_operational=false, acceptance_mode=manager.
 */
interface Props {
  elevator: ElevatorDetail
  open: boolean
  onClose: () => void
}

const DEFAULT_URGENCY = 'high'

export default function CreateRepairDialog({ elevator, open, onClose }: Props) {
  const { t } = useTranslation()
  const mutation = useCreateElevatorRepair(elevator.id)
  const [description, setDescription] = useState('')
  const [urgency, setUrgency] = useState<string>(DEFAULT_URGENCY)
  useOpenReset(open, () => {
    setDescription('')
    setUrgency(DEFAULT_URGENCY)
  })

  const submit = () =>
    mutation.mutate(
      {
        category: 'elevator',
        urgency,
        description: description.trim(),
        building_id: elevator.building_id,
        address: elevator.building_address,
        elevator_id: elevator.id,
        elevator_operational: false,
        acceptance_mode: 'manager',
      },
      { onSuccess: onClose },
    )

  return (
    <DialogShell
      open={open}
      title={t('elevators.repair.title')}
      onClose={onClose}
      onSubmit={submit}
      canSubmit={description.trim().length > 0}
      pending={mutation.isPending}
      submitLabel={t('elevators.repair.submit')}
      pendingLabel={t('common.creating')}
    >
      <p className="text-[13px] text-text-muted">
        {elevator.label} · {elevator.building_address}
      </p>
      <p className="text-[13px] text-text-muted">{t('elevators.repair.hint')}</p>
      <Field id="elevator-repair-urgency" label={t('elevators.repair.urgency')}>
        <Select id="elevator-repair-urgency" value={urgency} onChange={(e) => setUrgency(e.target.value)}>
          {URGENCIES.map((u) => (
            <option key={u} value={u}>{tUrgency(u, t)}</option>
          ))}
        </Select>
      </Field>
      <Field id="elevator-repair-description" label={t('elevators.repair.description')}>
        <Textarea
          id="elevator-repair-description"
          value={description}
          placeholder={t('elevators.repair.descriptionPlaceholder')}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
    </DialogShell>
  )
}
