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
 *
 * Третий режим — `rejectWithoutMedia`: массовое отклонение всех отчётов без
 * фото результата одной причиной; поле предзаполнено `initialReason`, чтобы
 * типовой случай закрывался одним кликом, но текст остаётся редактируемым.
 */
export type ReasonTarget =
  | { report: WorkReport; action: 'reject' | 'unpublish' }
  | { action: 'rejectWithoutMedia'; count: number; initialReason: string }

interface Props {
  target: ReasonTarget | null
  loading?: boolean
  onClose: () => void
  onSubmit: (reason: string) => void
}

function initialReasonFor(target: ReasonTarget | null): string {
  return target?.action === 'rejectWithoutMedia' ? target.initialReason : ''
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
    if (target) setReason(initialReasonFor(target))
  }

  const isOpen = target !== null
  const isBulk = target?.action === 'rejectWithoutMedia'
  const requiresReason = target?.action === 'reject' || isBulk
  const canSubmit = (!requiresReason || reason.trim().length > 0) && !loading

  const actionLabel = isBulk
    ? t('workReports.actions.rejectWithoutMedia', { count: target.count })
    : target?.action === 'reject'
      ? t('workReports.actions.reject')
      : t('workReports.actions.unpublish')
  const description = isBulk
    ? t('workReports.bulkRejectDesc', { count: target.count })
    : t('workReports.reasonDialogDesc')

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{actionLabel}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
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
            variant={requiresReason ? 'destructive' : 'default'}
            disabled={!canSubmit}
            onClick={() => onSubmit(reason.trim())}
          >
            {actionLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
