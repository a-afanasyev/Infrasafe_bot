import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Textarea } from '@/components/ui/textarea'
import { DialogShell, Field } from './DialogShell'
import { useOpenReset } from '../../hooks/useOpenReset'
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
  useOpenReset(status !== null, () => setReason(''))

  const submit = () => {
    if (!status) return
    mutation.mutate({ status, reason: reason.trim() || null }, { onSuccess: onClose })
  }

  return (
    <DialogShell
      open={status !== null}
      title={t('elevators.statusDialog.title', { status: status ? t(`elevators.status.${status}`) : '' })}
      onClose={onClose}
      onSubmit={submit}
      canSubmit
      pending={mutation.isPending}
      submitLabel={t('elevators.statusDialog.submit')}
    >
      <Field id="elevator-status-reason" label={t('elevators.statusDialog.reason')}>
        <Textarea
          id="elevator-status-reason"
          value={reason}
          maxLength={MAX_REASON_LEN}
          placeholder={t('elevators.statusDialog.reasonPlaceholder')}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
    </DialogShell>
  )
}
