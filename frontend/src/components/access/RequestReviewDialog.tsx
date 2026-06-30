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
import { useApartmentServingZones } from '../../hooks/useAccessRegistry'
import ZoneCheckboxes from './ZoneCheckboxes'
import type { AccessRequestRow } from '../../types/access'

/**
 * Диалог рассмотрения заявки жителя: подтверждение (зоны чекбоксами + опц.
 * комментарий) или отклонение (комментарий). Зоны — кандидаты по адресу жителя,
 * по умолчанию отмечены все обслуживающие зоны (§ зона привязана к адресу).
 */
export interface ReviewTarget {
  request: AccessRequestRow
  action: 'approve' | 'reject'
}

interface Props {
  target: ReviewTarget | null
  loading?: boolean
  onClose: () => void
  onSubmit: (data: {
    action: 'approve' | 'reject'
    comment?: string
    zoneIds?: number[]
  }) => void
}

export default function RequestReviewDialog({ target, loading, onClose, onSubmit }: Props) {
  const { t } = useTranslation()
  const [comment, setComment] = useState('')
  const [zoneIds, setZoneIds] = useState<number[]>([])

  const isApprove = target?.action === 'approve'
  const { data: servingZones } = useApartmentServingZones(
    isApprove ? (target?.request.apartment_id ?? null) : null,
  )

  // Сброс полей при смене target (render-time, как в ResolveDialog).
  const [zonesSyncedFor, setZonesSyncedFor] = useState<number | null>(null)
  const [prevTarget, setPrevTarget] = useState<ReviewTarget | null>(null)
  if (target !== prevTarget) {
    setPrevTarget(target)
    if (target) {
      setComment('')
      setZoneIds([])
      setZonesSyncedFor(null)
    }
  }

  // Дефолт «зона = адрес»: когда зоны загрузились — отметить все обслуживающие.
  if (
    isApprove &&
    servingZones &&
    target &&
    zonesSyncedFor !== target.request.id
  ) {
    setZonesSyncedFor(target.request.id)
    setZoneIds(servingZones.map((z) => z.id))
  }

  const isOpen = target !== null
  const plate =
    target?.request.plate_number_original ?? target?.request.plate_number_normalized ?? ''

  function handleSubmit() {
    if (!target || loading) return
    onSubmit({
      action: target.action,
      comment: comment.trim() ? comment.trim() : undefined,
      zoneIds: isApprove ? zoneIds : undefined,
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
              <Label>{t('accessControl.reviewDialog.zoneLabel')}</Label>
              <ZoneCheckboxes
                zones={servingZones ?? []}
                selected={zoneIds}
                onChange={setZoneIds}
                emptyText={t('accessControl.reviewDialog.noZones')}
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
