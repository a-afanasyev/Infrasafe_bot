import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { URGENCIES } from '../../constants'
import { tUrgency } from '../../i18n/apiMaps'
import { useCreateElevatorRepair } from '../../hooks/useElevators'
import type { ElevatorDetail } from '../../types/elevators'

/**
 * «Создать ремонт» из карточки лифта → POST /api/v2/callcenter/requests с
 * category=elevator, elevator_id, elevator_operational=false,
 * acceptance_mode=manager (поля читает бэкенд начиная с T6). Адрес — дома лифта.
 */
interface Props {
  elevator: ElevatorDetail
  open: boolean
  onClose: () => void
}

export default function CreateRepairDialog({ elevator, open, onClose }: Props) {
  const { t } = useTranslation()
  const mutation = useCreateElevatorRepair(elevator.id)
  const [description, setDescription] = useState('')
  const [urgency, setUrgency] = useState<string>('high')

  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setDescription('')
      setUrgency('high')
    }
  }

  const canSubmit = description.trim().length > 0 && !mutation.isPending

  const submit = () =>
    mutation.mutate(
      {
        category: 'elevator',
        urgency,
        description: description.trim(),
        address: elevator.building_address,
        elevator_id: elevator.id,
        elevator_operational: false,
        acceptance_mode: 'manager',
      },
      { onSuccess: onClose },
    )

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('elevators.repair.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-[13px] text-text-muted">
          {elevator.label} · {elevator.building_address}
        </p>
        <p className="text-[13px] text-text-muted">{t('elevators.repair.hint')}</p>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="elevator-repair-urgency">{t('elevators.repair.urgency')}</Label>
          <Select id="elevator-repair-urgency" value={urgency} onChange={(e) => setUrgency(e.target.value)}>
            {URGENCIES.map((u) => (
              <option key={u} value={u}>{tUrgency(u, t)}</option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="elevator-repair-description">{t('elevators.repair.description')}</Label>
          <Textarea
            id="elevator-repair-description"
            value={description}
            placeholder={t('elevators.repair.descriptionPlaceholder')}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {mutation.isPending ? t('common.creating') : t('elevators.repair.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
