import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { useMyTransfers, useRespondTransfer, type TwaTransfer } from '../hooks/useTransfers'
import { useTelegramSDK } from '../hooks/useTelegramSDK'
import { getErrorMessage } from '../utils/errors'

const STATUS_TONE: Record<string, string> = {
  pending: 'text-amber-600',
  assigned: 'text-blue-600',
  accepted: 'text-emerald-600',
  completed: 'text-emerald-600',
  rejected: 'text-red-500',
  cancelled: 'text-gray-400',
}

/**
 * «Мои передачи» (TWA PR-T2): передачи текущего исполнителя.
 * Для назначенных ему (can_respond) — кнопки Принять/Отклонить через
 * POST /executor/shifts/transfers/{id}/respond.
 */
export default function TransfersList() {
  const { t } = useTranslation()
  const { haptic } = useTelegramSDK()
  const { data: transfers = [], isLoading } = useMyTransfers()
  const respond = useRespondTransfer()

  if (isLoading || transfers.length === 0) return null

  const act = async (transfer: TwaTransfer, action: 'accept' | 'reject') => {
    try {
      await respond.mutateAsync({ id: transfer.id, action })
      haptic('notification')
      toast.success(
        t(action === 'accept' ? 'twa.exec.transfer.toastAccepted' : 'twa.exec.transfer.toastRejected'),
      )
    } catch (err) {
      haptic('notification')
      const key = getErrorMessage(err, '')
      const localized = t(`twa.exec.transfer.errors.${key}`, '')
      toast.error(localized || t('twa.exec.transfer.toastRespondFailed'))
    }
  }

  return (
    <div className="mt-6">
      <h2 className="text-[14px] font-bold text-gray-900 dark:text-gray-100 mb-2">
        {t('twa.exec.transfer.myTransfers')}
      </h2>

      {transfers.map((tr) => {
        const start = tr.shift_start_time ? new Date(tr.shift_start_time) : null
        return (
          <div
            key={tr.id}
            className="bg-white dark:bg-gray-800 rounded-2xl p-3.5 border border-gray-100 dark:border-gray-700 mb-2"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] text-gray-400">
                {tr.direction === 'outgoing'
                  ? t('twa.exec.transfer.outgoing')
                  : t('twa.exec.transfer.incoming')}{' '}
                · #{tr.shift_id}
              </span>
              <span className={`text-[11px] font-semibold ${STATUS_TONE[tr.status] ?? 'text-gray-400'}`}>
                {t(`twa.exec.transfer.status.${tr.status}`, tr.status)}
              </span>
            </div>
            <div className="text-[12px] text-gray-600 dark:text-gray-400">
              {t(`transferReason.${tr.reason}`, tr.reason)}
              {start && ` · ${start.toLocaleDateString()} ${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
            </div>
            {tr.comment && (
              <div className="text-[11px] text-gray-400 mt-0.5">{tr.comment}</div>
            )}

            {tr.can_respond && (
              <div className="flex gap-2 mt-2.5">
                <button
                  onClick={() => act(tr, 'accept')}
                  disabled={respond.isPending}
                  className="flex-1 py-2 rounded-xl text-[13px] font-semibold bg-emerald-500 text-white disabled:opacity-50"
                >
                  {t('twa.exec.transfer.accept')}
                </button>
                <button
                  onClick={() => act(tr, 'reject')}
                  disabled={respond.isPending}
                  className="flex-1 py-2 rounded-xl text-[13px] font-semibold bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 disabled:opacity-50"
                >
                  {t('twa.exec.transfer.reject')}
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
