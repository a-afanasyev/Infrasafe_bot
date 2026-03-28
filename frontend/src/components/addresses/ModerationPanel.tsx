import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  usePendingModeration,
  useApproveModeration,
  useRejectModeration,
} from '../../hooks/useAddresses'
import type { ModerationItem } from '../../types/api'
import EmptyState from '../shared/EmptyState'
import LoadingSpinner from '../shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { formatDate as fmtDate } from '../../i18n/formatters'

export default function ModerationPanel() {
  const { t } = useTranslation()
  const { data: items = [], isLoading } = usePendingModeration()
  const approve = useApproveModeration()
  const reject = useRejectModeration()

  const [rejectingId, setRejectingId] = useState<number | null>(null)
  const [rejectComment, setRejectComment] = useState('')
  const [pendingActionId, setPendingActionId] = useState<number | null>(null)

  if (isLoading) return <LoadingSpinner />

  if (items.length === 0) {
    return (
      <EmptyState
        icon="&#10003;"
        title={t('moderationPanel.noPending')}
        subtitle={t('moderationPanel.allReviewed')}
      />
    )
  }

  const handleApprove = (id: number) => {
    setPendingActionId(id)
    approve.mutate(id, { onSettled: () => setPendingActionId(null) })
  }

  const handleStartReject = (id: number) => {
    setRejectingId(id)
    setRejectComment('')
  }

  const handleCancelReject = () => {
    setRejectingId(null)
    setRejectComment('')
  }

  const handleSubmitReject = (id: number) => {
    if (rejectComment.trim().length < 3) return
    setPendingActionId(id)
    reject.mutate(
      { id, comment: rejectComment.trim() },
      { onSuccess: () => handleCancelReject(), onSettled: () => setPendingActionId(null) },
    )
  }

  const localFormatDate = (dateStr: string | null) => {
    if (!dateStr) return null
    return fmtDate(dateStr, { dateStyle: 'short' })
  }

  const buildAddress = (item: ModerationItem) => {
    const parts: string[] = []
    if (item.yard_name) parts.push(item.yard_name)
    if (item.building_address) parts.push(item.building_address)
    parts.push(`${t('moderationPanel.aptShort')} ${item.apartment_number}`)
    return parts.join(' / ')
  }

  return (
    <div className="flex flex-col gap-3">
      {items.map(item => (
        <div key={item.id} className="bg-bg-card border border-border-default rounded-default p-4 px-5 flex flex-col gap-2.5">
          {/* Top row: name + badge */}
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="font-[family-name:var(--font-display)] font-semibold text-[15px] text-text-primary">
              {item.user_name || t('moderationPanel.noName')}
            </span>
            {item.user_phone && (
              <span className="text-[13px] text-text-muted font-[family-name:var(--font-mono)]">
                {item.user_phone}
              </span>
            )}
            <span className={cn(
              'rounded-xl px-2.5 py-0.5 text-[11px] font-semibold font-[family-name:var(--font-mono)] inline-block',
              item.is_owner
                ? 'bg-emerald/[.13] text-emerald'
                : 'bg-blue/[.13] text-blue'
            )}>
              {item.is_owner ? t('moderationPanel.owner') : t('moderationPanel.tenant')}
            </span>
          </div>

          {/* Address */}
          <div className="text-[13px] text-text-secondary font-[family-name:var(--font-display)] leading-relaxed">
            {buildAddress(item)}
          </div>

          {/* Date */}
          {item.requested_at && (
            <div className="text-xs text-text-muted font-[family-name:var(--font-display)]">
              {t('moderationPanel.requestFrom', { date: localFormatDate(item.requested_at) })}
            </div>
          )}

          {/* Actions */}
          {rejectingId === item.id ? (
            /* Rejection form */
            <div className="flex flex-col gap-2">
              <Textarea
                value={rejectComment}
                onChange={e => setRejectComment(e.target.value)}
                placeholder={t('moderationPanel.rejectReason')}
                autoFocus
              />
              <div className="flex items-center gap-2.5">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleSubmitReject(item.id)}
                  disabled={rejectComment.trim().length < 3 || reject.isPending}
                >
                  {reject.isPending ? t('moderationPanel.submitting') : t('moderationPanel.submit')}
                </Button>
                <button
                  onClick={handleCancelReject}
                  className="bg-transparent border-none cursor-pointer text-[13px] text-text-muted font-[family-name:var(--font-display)] underline p-0"
                >
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          ) : (
            /* Approve / Reject buttons */
            <div className="flex gap-2">
              <Button
                onClick={() => handleApprove(item.id)}
                disabled={pendingActionId !== null}
                size="sm"
              >
                {pendingActionId === item.id && approve.isPending ? t('moderationPanel.approving') : t('moderationPanel.approve')}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleStartReject(item.id)}
              >
                {t('moderationPanel.reject')}
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
