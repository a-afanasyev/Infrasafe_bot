import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { useInitiateTransfer } from '../hooks/useTransfers'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { getErrorMessage } from '../utils/errors'

const REASONS = ['illness', 'emergency', 'workload', 'vacation', 'other'] as const
const URGENCIES = ['low', 'normal', 'high', 'critical'] as const

interface Props {
  shiftId: number
  onClose: () => void
}

/**
 * Bottom-sheet инициации передачи смены исполнителем (TWA PR-T2).
 * Причина/срочность — пилюлями (как CreatePage), комментарий — textarea.
 * Серверные ключи: reason illness/emergency/workload/vacation/other,
 * urgency low/normal/high/critical.
 */
export default function TransferSheet({ shiftId, onClose }: Props) {
  const { t } = useTranslation()
  const { haptic } = useTelegramSDK()
  const initiate = useInitiateTransfer()
  const [reason, setReason] = useState<string>('illness')
  const [urgency, setUrgency] = useState<string>('normal')
  const [comment, setComment] = useState('')

  const submit = async () => {
    try {
      await initiate.mutateAsync({
        shift_id: shiftId,
        reason,
        urgency_level: urgency,
        comment: comment.trim() || undefined,
      })
      haptic('notification')
      toast.success(t('twa.exec.transfer.toastCreated'))
      onClose()
    } catch (err) {
      haptic('notification')
      const key = getErrorMessage(err, '')
      const localized = t(`twa.exec.transfer.errors.${key}`, '')
      toast.error(localized || t('twa.exec.transfer.toastCreateFailed'))
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end" onClick={onClose}>
      <div
        className="w-full bg-white dark:bg-gray-800 rounded-t-2xl p-4 pb-6 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-semibold text-[15px] text-gray-900 dark:text-gray-100 mb-3">
          {t('twa.exec.transfer.title')}
        </h3>

        <p className="text-[12px] text-gray-500 mb-1.5">{t('twa.exec.transfer.reason')}</p>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {REASONS.map((r) => (
            <button
              key={r}
              onClick={() => { setReason(r); haptic('selection') }}
              className={`px-3 py-1.5 rounded-full text-[12px] font-medium ${
                reason === r
                  ? 'bg-emerald-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
              }`}
            >
              {t(`transferReason.${r}`)}
            </button>
          ))}
        </div>

        <p className="text-[12px] text-gray-500 mb-1.5">{t('twa.exec.transfer.urgency')}</p>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {URGENCIES.map((u) => (
            <button
              key={u}
              onClick={() => { setUrgency(u); haptic('selection') }}
              className={`px-3 py-1.5 rounded-full text-[12px] font-medium ${
                urgency === u
                  ? 'bg-emerald-500 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
              }`}
            >
              {t(`twa.exec.transfer.urgencyLevels.${u}`)}
            </button>
          ))}
        </div>

        <p className="text-[12px] text-gray-500 mb-1.5">{t('twa.exec.transfer.comment')}</p>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={t('twa.exec.transfer.commentPlaceholder')}
          className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] min-h-[80px] resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500 mb-3"
        />

        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 py-3 rounded-xl text-[13px] font-semibold bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
          >
            {t('twa.exec.transfer.cancel')}
          </button>
          <button
            onClick={submit}
            disabled={initiate.isPending}
            className="flex-1 py-3 rounded-xl text-[13px] font-semibold bg-emerald-500 text-white disabled:opacity-50"
          >
            {t('twa.exec.transfer.submit')}
          </button>
        </div>
      </div>
    </div>
  )
}
