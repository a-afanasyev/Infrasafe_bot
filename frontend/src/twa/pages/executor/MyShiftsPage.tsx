import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { ArrowLeft, Clock } from 'lucide-react'

export default function MyShiftsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showBackButton } = useTelegramSDK()

  useEffect(() => {
    return showBackButton(() => navigate(-1))
  }, [showBackButton, navigate])

  const { data: shifts = [], isLoading } = useQuery({
    queryKey: ['my-shifts'],
    queryFn: () => twaClient.get('/api/v2/executor/shifts/me', { params: { limit: 20 } }).then(r => r.data),
  })

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-emerald-500 text-[13px] mb-3">
        <ArrowLeft size={16} /> {t('common.back')}
      </button>
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.myShifts.title')}</h1>

      {isLoading && <p className="text-center text-gray-400 py-8">{t('common.loading')}</p>}

      {shifts.map((s: any) => {
        const start = s.start_time ? new Date(s.start_time) : null
        const end = s.end_time ? new Date(s.end_time) : null
        const isActive = s.status === 'active'
        return (
          <div key={s.id} className={`bg-white dark:bg-gray-800 rounded-2xl p-3.5 border mb-2 ${isActive ? 'border-emerald-300 dark:border-emerald-700' : 'border-gray-100 dark:border-gray-700'}`}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <Clock size={14} className={isActive ? 'text-emerald-500' : 'text-gray-400'} />
                <span className={`text-[12px] font-semibold ${isActive ? 'text-emerald-600' : 'text-gray-500'}`}>
                  {isActive ? t('twa.exec.myShifts.active') : t('twa.exec.myShifts.completed')}
                </span>
              </div>
              <span className="text-[11px] text-gray-400">#{s.id}</span>
            </div>
            <div className="text-[12px] text-gray-600 dark:text-gray-400">
              {start?.toLocaleDateString()} {start?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              {end && ` — ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
            </div>
          </div>
        )
      })}
    </div>
  )
}
