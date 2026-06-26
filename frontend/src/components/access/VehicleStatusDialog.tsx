import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import type { VehicleRow, VehicleStatus } from '../../types/access'

/**
 * Диалог смены статуса авто: блокировка (обязательная причина), разблокировка
 * и архивация — с подтверждением. Для block/archive — деструктивный акцент.
 */
export interface StatusTarget {
  vehicle: VehicleRow
  status: VehicleStatus
}

interface Props {
  target: StatusTarget | null
  loading?: boolean
  onClose: () => void
  onSubmit: (data: { status: VehicleStatus; reason?: string }) => void
}

export default function VehicleStatusDialog({ target, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')

  // Сброс причины при смене target (render-time, как в ResolveDialog).
  const [prevTarget, setPrevTarget] = useState<StatusTarget | null>(null)
  if (target !== prevTarget) {
    setPrevTarget(target)
    if (target) setReason('')
  }

  const isOpen = target !== null
  const status = target?.status
  const isBlock = status === 'blocked'
  const isDestructive = status === 'blocked' || status === 'archived'
  const reasonOk = !isBlock || reason.trim().length > 0
  const canSubmit = reasonOk && !loading

  const plate = target?.vehicle.plate_number_original ?? target?.vehicle.plate_number_normalized ?? ''

  function titleKey() {
    if (status === 'blocked') return 'accessControl.statusDialog.blockTitle'
    if (status === 'archived') return 'accessControl.statusDialog.archiveTitle'
    return 'accessControl.statusDialog.unblockTitle'
  }
  function descKey() {
    if (status === 'blocked') return 'accessControl.statusDialog.blockDesc'
    if (status === 'archived') return 'accessControl.statusDialog.archiveDesc'
    return 'accessControl.statusDialog.unblockDesc'
  }
  function confirmKey() {
    if (status === 'blocked') return 'accessControl.actions.block'
    if (status === 'archived') return 'accessControl.actions.archive'
    return 'accessControl.actions.unblock'
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(titleKey())}</DialogTitle>
          <DialogDescription>{t(descKey(), { plate })}</DialogDescription>
        </DialogHeader>

        {isBlock && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="vehicle-block-reason">
              {t('accessControl.statusDialog.reasonLabel')}
            </Label>
            <Textarea
              id="vehicle-block-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t('accessControl.statusDialog.reasonPlaceholder')}
              rows={3}
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={isDestructive ? 'destructive' : 'default'}
            disabled={!canSubmit}
            onClick={() =>
              status &&
              onSubmit({ status, reason: isBlock ? reason.trim() : undefined })
            }
          >
            {t(confirmKey())}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
