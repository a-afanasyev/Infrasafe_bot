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
import { useAccessRequestDetail } from '../../hooks/useAccessRegistry'
import { AccessStatusBadge } from './AccessBadges'
import { formatDateTime } from '../../utils/accessFormat'
import LoadingSpinner from '../shared/LoadingSpinner'
import { MetaField, ApplicantAddressZones } from './AccessMeta'

/**
 * Деталь заявки на авто (read-only): заявитель, адрес, обслуживающие зоны,
 * связанный авто и история рассмотрения. Approve/Reject — в RequestReviewDialog.
 */
interface Props {
  requestId: number | null
  onClose: () => void
  onApprove?: () => void
  onReject?: () => void
}

export default function RequestDetailDialog({ requestId, onClose, onApprove, onReject }: Props) {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useAccessRequestDetail(requestId)
  const req = data?.request
  const isPending = req?.status === 'pending'

  return (
    <Dialog open={requestId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('accessControl.requestDetail.title')}</DialogTitle>
          <DialogDescription>
            {req ? (
              <span className="font-mono">
                {req.plate_number_original || req.plate_number_normalized || '—'}
              </span>
            ) : (
              ' '
            )}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <LoadingSpinner />}
        {isError && <p className="text-[13px] text-red">{t('common.error')}</p>}

        {data && req && (
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 gap-3">
              <MetaField
                label={t('accessControl.columns.status')}
                value={<AccessStatusBadge status={req.status} />}
              />
              <MetaField
                label={t('accessControl.requests.relation')}
                value={
                  req.relation_type
                    ? t(`accessControl.relationType.${req.relation_type}`, {
                        defaultValue: req.relation_type,
                      })
                    : '—'
                }
              />
              <MetaField label={t('accessControl.requests.created')} value={formatDateTime(req.created_at)} />
              <MetaField
                label={t('accessControl.requests.reviewedAt')}
                value={formatDateTime(req.reviewed_at)}
              />
              {req.review_comment && (
                <MetaField label={t('accessControl.requests.comment')} value={req.review_comment} />
              )}
            </div>

            <ApplicantAddressZones
              applicant={data.applicant}
              address={data.address}
              zones={data.serving_zones}
              zonesLabel={t('accessControl.requestDetail.servingZones')}
            />

            {data.vehicle && (
              <MetaField
                label={t('accessControl.requestDetail.linkedVehicle')}
                value={
                  <span className="font-mono">
                    {data.vehicle.plate_number_original || data.vehicle.plate_number_normalized}
                  </span>
                }
              />
            )}
          </div>
        )}

        {isPending && (onApprove || onReject) && (
          <DialogFooter>
            {onReject && (
              <Button variant="destructive" onClick={onReject}>
                {t('accessControl.actions.reject')}
              </Button>
            )}
            {onApprove && (
              <Button onClick={onApprove}>{t('accessControl.actions.approve')}</Button>
            )}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
