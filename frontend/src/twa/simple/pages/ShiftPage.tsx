import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ClipboardList, Play, Square } from 'lucide-react'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { useExecutorTasks } from '../../hooks/useExecutorTasks'
import { notifyError } from '../../utils/errors'
import { useCurrentShift } from '../api'
import { useBackTo, useElapsed } from '../hooks/useSimpleNav'
import { ConfirmSheet, ErrorBlock, Loading } from '../components/Ui'
import { useCompletionQueue } from '../queue/CompletionQueue'

/** Смена: круглая кнопка 200 px «Начать» / «Закончить» и таймер. */
export default function ShiftPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { notify } = useTelegramSDK()
  const { flushNow } = useCompletionQueue()
  const [confirmEnd, setConfirmEnd] = useState(false)
  useBackTo('/twa/s')

  const { data: shift, isLoading, isError, refetch } = useCurrentShift()
  const { data: tasks = [] } = useExecutorTasks('active')
  const elapsed = useElapsed(shift?.start_time)

  const refreshAfterShift = () => {
    queryClient.invalidateQueries({ queryKey: ['twa', 'current-shift'] })
    queryClient.invalidateQueries({ queryKey: ['twa', 'my-shifts'] })
    queryClient.invalidateQueries({ queryKey: ['twa', 'simple', 'pool'] })
  }

  // Эндпоинты — те же, что у pages/executor/ShiftPage.
  const start = useMutation({
    mutationFn: () => twaClient.post('/api/v2/executor/shifts/start', {}),
    onSuccess: () => {
      notify('success')
      refreshAfterShift()
      // «Готово», отложенное из-за «нет смены», уходит сразу.
      flushNow()
    },
    onError: (err: unknown) => {
      notify('error')
      notifyError(err, t('twa.simple.shift.failed'))
    },
  })

  const end = useMutation({
    mutationFn: (id: number) => twaClient.post(`/api/v2/executor/shifts/${id}/end`),
    onSuccess: () => {
      notify('success')
      setConfirmEnd(false)
      refreshAfterShift()
    },
    onError: (err: unknown) => {
      notify('error')
      notifyError(err, t('twa.simple.shift.failed'))
    },
  })

  if (isLoading) return <main className="p-3"><Loading /></main>
  if (isError && shift === undefined) return <main className="p-3"><ErrorBlock onRetry={() => void refetch()} /></main>

  const active = !!shift?.id
  return (
    <main className="min-h-[80vh] p-3 flex flex-col items-center justify-center gap-6 text-center">
      <p className="text-[24px] font-bold">{active ? t('twa.simple.shift.on') : t('twa.simple.shift.off')}</p>
      {active && <p className="text-[40px] font-mono font-bold text-emerald-600 dark:text-emerald-400" data-testid="shift-timer">{elapsed}</p>}
      <button
        type="button"
        disabled={start.isPending || end.isPending}
        onClick={() => (active ? setConfirmEnd(true) : start.mutate())}
        className={`w-[200px] h-[200px] rounded-full flex flex-col items-center justify-center gap-2 text-white text-[26px] font-bold shadow-lg disabled:opacity-60 active:scale-95 transition-transform ${
          active ? 'bg-red-600' : 'bg-emerald-600'
        }`}
      >
        {active ? <Square size={56} fill="currentColor" aria-hidden /> : <Play size={56} fill="currentColor" aria-hidden />}
        {active ? t('twa.simple.shift.end') : t('twa.simple.shift.start')}
      </button>

      {confirmEnd && shift && (
        <ConfirmSheet
          title={t('twa.simple.shift.confirmEnd')}
          busy={end.isPending}
          onNo={() => setConfirmEnd(false)}
          onYes={() => end.mutate(shift.id)}
        >
          <p className="flex items-center justify-center gap-2 text-[20px] font-semibold text-orange-700 dark:text-orange-300">
            <ClipboardList size={26} aria-hidden /> {t('twa.simple.shift.openTasks', { count: tasks.length })}
          </p>
        </ConfirmSheet>
      )}
    </main>
  )
}
