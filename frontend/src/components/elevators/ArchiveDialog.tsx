import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
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

  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) setReason('')
  }

  const canSubmit = reason.trim().length > 0 && !mutation.isPending

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('elevators.archiveDialog.title')}</DialogTitle>
        </DialogHeader>
        <p className="text-[13px] text-text-muted">{t('elevators.archiveDialog.hint')}</p>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="elevator-archive-reason">{t('elevators.archiveDialog.reason')}</Label>
          <Textarea
            id="elevator-archive-reason"
            value={reason}
            maxLength={MAX_REASON_LEN}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="destructive"
            disabled={!canSubmit}
            onClick={() => mutation.mutate(reason.trim(), { onSuccess: onClose })}
          >
            {mutation.isPending ? t('common.saving') : t('elevators.archiveDialog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
