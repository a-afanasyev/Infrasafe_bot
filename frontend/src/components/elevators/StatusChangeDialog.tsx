import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useSetElevatorStatus } from '../../hooks/useElevators'
import { MAX_REASON_LEN, type ElevatorStatus } from '../../types/elevators'

/**
 * Смена статуса лифта с необязательной причиной → PUT /{id}/status.
 * `notified_residents` показывает хук в toast.
 */
interface Props {
  elevatorId: number
  status: ElevatorStatus | null // null = закрыт
  onClose: () => void
}

export default function StatusChangeDialog({ elevatorId, status, onClose }: Props) {
  const { t } = useTranslation()
  const mutation = useSetElevatorStatus(elevatorId)
  const [reason, setReason] = useState('')

  // Render-time reset при открытии (паттерн MaterialFormDialog — без useEffect)
  const [prevStatus, setPrevStatus] = useState<ElevatorStatus | null>(null)
  if (status !== prevStatus) {
    setPrevStatus(status)
    if (status) setReason('')
  }

  const submit = () => {
    if (!status) return
    mutation.mutate(
      { status, reason: reason.trim() || null },
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog open={status !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {t('elevators.statusDialog.title', { status: status ? t(`elevators.status.${status}`) : '' })}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="elevator-status-reason">{t('elevators.statusDialog.reason')}</Label>
          <Textarea
            id="elevator-status-reason"
            value={reason}
            maxLength={MAX_REASON_LEN}
            placeholder={t('elevators.statusDialog.reasonPlaceholder')}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending ? t('common.saving') : t('elevators.statusDialog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
