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
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { WorkReport } from '../../types/workReports'

/**
 * Reject/unpublish reason dialog for WorkReportsPage — mirrors
 * components/access/ResolveDialog.tsx's "type a reason, then confirm" shape,
 * ported to the workReports.* i18n namespace. Reject requires a non-empty
 * reason; unpublish does not (see canSubmit below).
 */
export interface ReasonTarget {
  report: WorkReport
  action: 'reject' | 'unpublish'
}

interface Props {
  target: ReasonTarget | null
  loading?: boolean
  onClose: () => void
  onSubmit: (reason: string) => void
}

export default function ReasonDialog({ target, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')

  // Сброс поля при смене target — render-time pattern (см. ResolveDialog.tsx):
  // setState-в-effect ругается линтером, а без сброса текст «перетекал» бы
  // между отчётами.
  const [prevTarget, setPrevTarget] = useState<ReasonTarget | null>(null)
  if (target !== prevTarget) {
    setPrevTarget(target)
    if (target) setReason('')
  }

  const isOpen = target !== null
  const isReject = target?.action === 'reject'
  const canSubmit = (!isReject || reason.trim().length > 0) && !loading

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isReject ? t('workReports.actions.reject') : t('workReports.actions.unpublish')}
          </DialogTitle>
          <DialogDescription>{t('workReports.reasonDialogDesc')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="wr-reason">{t('workReports.reasonPlaceholder')}</Label>
          <Textarea
            id="wr-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t('workReports.reasonPlaceholder')}
            rows={3}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={isReject ? 'destructive' : 'default'}
            disabled={!canSubmit}
            onClick={() => onSubmit(reason.trim())}
          >
            {isReject ? t('workReports.actions.reject') : t('workReports.actions.unpublish')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
