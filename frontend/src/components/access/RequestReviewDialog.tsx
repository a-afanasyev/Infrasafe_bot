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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import type { AccessRequestRow } from '../../types/access'

/**
 * Диалог рассмотрения заявки жителя: подтверждение (опц. зона + комментарий) или
 * отклонение (комментарий). Комментарий опционален, зона — только при approve.
 */
export interface ReviewTarget {
  request: AccessRequestRow
  action: 'approve' | 'reject'
}

interface Props {
  target: ReviewTarget | null
  loading?: boolean
  onClose: () => void
  onSubmit: (data: { action: 'approve' | 'reject'; comment?: string; zoneId?: number }) => void
}

export default function RequestReviewDialog({ target, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const [comment, setComment] = useState('')
  const [zoneId, setZoneId] = useState('')

  // Сброс полей при смене target (render-time, как в ResolveDialog).
  const [prevTarget, setPrevTarget] = useState<ReviewTarget | null>(null)
  if (target !== prevTarget) {
    setPrevTarget(target)
    if (target) {
      setComment('')
      setZoneId('')
    }
  }

  const isOpen = target !== null
  const isApprove = target?.action === 'approve'
  const plate =
    target?.request.plate_number_original ?? target?.request.plate_number_normalized ?? ''

  function handleSubmit() {
    if (!target || loading) return
    const zoneNum = Number(zoneId)
    onSubmit({
      action: target.action,
      comment: comment.trim() ? comment.trim() : undefined,
      zoneId: isApprove && zoneId.trim() && Number.isFinite(zoneNum) ? zoneNum : undefined,
    })
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isApprove
              ? t('accessControl.reviewDialog.approveTitle')
              : t('accessControl.reviewDialog.rejectTitle')}
          </DialogTitle>
          <DialogDescription>
            {isApprove
              ? t('accessControl.reviewDialog.approveDesc', { plate })
              : t('accessControl.reviewDialog.rejectDesc', { plate })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {isApprove && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="review-zone">{t('accessControl.reviewDialog.zoneLabel')}</Label>
              <Input
                id="review-zone"
                type="number"
                value={zoneId}
                onChange={(e) => setZoneId(e.target.value)}
                placeholder={t('accessControl.reviewDialog.zonePlaceholder')}
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="review-comment">{t('accessControl.reviewDialog.commentLabel')}</Label>
            <Textarea
              id="review-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={t('accessControl.reviewDialog.commentPlaceholder')}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={isApprove ? 'default' : 'destructive'}
            disabled={loading}
            onClick={handleSubmit}
          >
            {isApprove
              ? t('accessControl.actions.approve')
              : t('accessControl.actions.reject')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
