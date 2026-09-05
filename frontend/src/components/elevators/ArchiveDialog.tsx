import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Textarea } from '@/components/ui/textarea'
import { DialogShell, Field } from './DialogShell'
import { useOpenReset } from '../../hooks/useOpenReset'
import { useArchiveElevator } from '../../hooks/useElevators'
import { MAX_REASON_LEN } from '../../types/elevators'

/** Архивация лифта с обязательной причиной (1..500) → POST /{id}/archive. */
interface Props {
  elevatorId: number
  open: boolean
  onClose: () => void
}

export default function ArchiveDialog({ elevatorId, open, onClose }: Props) {
  const { t } = useTranslation()
  const mutation = useArchiveElevator(elevatorId)
  const [reason, setReason] = useState('')
  useOpenReset(open, () => setReason(''))

  return (
    <DialogShell
      open={open}
      title={t('elevators.archiveDialog.title')}
      onClose={onClose}
      onSubmit={() => mutation.mutate(reason.trim(), { onSuccess: onClose })}
      canSubmit={reason.trim().length > 0}
      pending={mutation.isPending}
      submitLabel={t('elevators.archiveDialog.submit')}
      submitVariant="destructive"
    >
      <p className="text-[13px] text-text-muted">{t('elevators.archiveDialog.hint')}</p>
      <Field id="elevator-archive-reason" label={t('elevators.archiveDialog.reason')}>
        <Textarea
          id="elevator-archive-reason"
          value={reason}
          maxLength={MAX_REASON_LEN}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
    </DialogShell>
  )
}
