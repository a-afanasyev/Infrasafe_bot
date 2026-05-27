import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { getErrorMessage } from '../../utils/errors'

export default function CompletionReport() {
  const { number } = useParams()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()
  const [report, setReport] = useState('')

  const completeMutation = useMutation({
    mutationFn: () => twaClient.patch(`/api/v2/requests/${number}`, {
      status: 'Выполнена',
      completion_report: report || undefined,
    }),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['executor-tasks'] })
      queryClient.invalidateQueries({ queryKey: ['request', number] })
      navigate('/twa/exec')
    },
    onError: (err: unknown) => {
      haptic('notification')
      toast.error(getErrorMessage(err, 'Не удалось завершить заявку'))
    },
  })

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.report.title')}</h1>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-4 border border-gray-100 dark:border-gray-700 mb-4">
        <p className="text-[12px] text-gray-500 mb-2">{t('twa.exec.report.description')}</p>
        <textarea
          value={report}
          onChange={(e) => setReport(e.target.value)}
          placeholder={t('twa.exec.report.placeholder')}
          className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-3 text-[13px] min-h-[100px] resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
      </div>

      <button
        onClick={() => completeMutation.mutate()}
        disabled={completeMutation.isPending}
        className="w-full bg-emerald-500 text-white py-3 rounded-xl font-semibold disabled:opacity-50"
      >
        {completeMutation.isPending ? t('common.loading') : t('twa.exec.report.submit')}
      </button>
    </div>
  )
}
