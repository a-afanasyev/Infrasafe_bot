import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { notifyError } from '../../utils/errors'
import { Play, Square, Clock, CalendarDays, ChevronRight } from 'lucide-react'

export default function ShiftPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { haptic } = useTelegramSDK()
  const [elapsed, setElapsed] = useState('')

  const { data: currentShift } = useQuery({
    queryKey: ['twa', 'current-shift'],
    queryFn: () => twaClient.get('/api/v2/executor/shifts/current').then(r => r.data),
    refetchInterval: 30_000,
  })

  // Timer
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- намеренная синхронизация таймера смены с внешним состоянием shift
    if (!currentShift?.start_time) { setElapsed(''); return }
    const start = new Date(currentShift.start_time).getTime()
    const tick = () => {
      const diff = Date.now() - start
      const h = Math.floor(diff / 3600000)
      const m = Math.floor((diff % 3600000) / 60000)
      const s = Math.floor((diff % 60000) / 1000)
      setElapsed(`${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [currentShift?.start_time])

  const startMutation = useMutation({
    mutationFn: () => twaClient.post('/api/v2/executor/shifts/start', {}),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['twa', 'current-shift'] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'my-shifts'] })
    },
    onError: (err: unknown) => {
      haptic('notification')
      notifyError(err, 'Не удалось начать смену')
    },
  })

  const endMutation = useMutation({
    mutationFn: (id: number) => twaClient.post(`/api/v2/executor/shifts/${id}/end`),
    onSuccess: () => {
      haptic('notification')
      queryClient.invalidateQueries({ queryKey: ['twa', 'current-shift'] })
      queryClient.invalidateQueries({ queryKey: ['twa', 'my-shifts'] })
    },
    onError: (err: unknown) => {
      haptic('notification')
      notifyError(err, 'Не удалось завершить смену')
    },
  })

  const isActive = !!currentShift?.id

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-6">{t('twa.exec.shift.title')}</h1>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 text-center">
        {isActive ? (
          <>
            <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mx-auto mb-3">
              <Clock size={28} className="text-emerald-500" />
            </div>
            <p className="text-[12px] text-gray-500 mb-1">{t('twa.exec.shift.active')}</p>
            <p className="text-3xl font-mono font-bold text-emerald-500 mb-4">{elapsed}</p>
            <button
              onClick={() => endMutation.mutate(currentShift.id)}
              disabled={endMutation.isPending}
              className="w-full flex items-center justify-center gap-2 bg-red-500 text-white py-3 rounded-xl font-semibold disabled:opacity-50"
            >
              <Square size={18} /> {t('twa.exec.shift.end')}
            </button>
          </>
        ) : (
          <>
            <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mx-auto mb-3">
              <Play size={28} className="text-gray-400" />
            </div>
            <p className="text-[14px] text-gray-500 mb-4">{t('twa.exec.shift.inactive')}</p>
            <button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              className="w-full flex items-center justify-center gap-2 bg-emerald-500 text-white py-3 rounded-xl font-semibold disabled:opacity-50"
            >
              <Play size={18} /> {t('twa.exec.shift.start')}
            </button>
          </>
        )}
      </div>

      {/* Вход в «Мои смены» — список смен + инициация/приём передачи (PR-T2) */}
      <button
        onClick={() => { haptic('selection'); navigate('/twa/exec/shifts') }}
        className="w-full mt-3 flex items-center justify-between bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl p-4 text-left"
      >
        <span className="flex items-center gap-2 text-[14px] font-medium text-gray-900 dark:text-gray-100">
          <CalendarDays size={18} className="text-emerald-500" /> {t('twa.exec.myShifts.title')}
        </span>
        <ChevronRight size={18} className="text-gray-400" />
      </button>
    </div>
  )
}
