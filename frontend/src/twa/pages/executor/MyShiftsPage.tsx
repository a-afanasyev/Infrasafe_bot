import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { twaClient } from '../../twaClient'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { ArrowLeft, Clock, Repeat } from 'lucide-react'
import { useMyTransfers } from '../../hooks/useTransfers'
import TransferSheet from '../../components/TransferSheet'
import TransfersList from '../../components/TransfersList'

// Статусы передачи, занимающие смену (нельзя инициировать вторую).
const ACTIVE_TRANSFER_STATUSES = ['pending', 'assigned', 'accepted']

// Backend /executor/shifts/me has no status filter and caps at limit=100.
// We fetch the cap and filter client-side; if we actually hit 100 rows we
// surface an honest "showing last 100" note instead of silently truncating.
const SHIFTS_LIMIT = 100

type Filter = 'all' | 'active' | 'completed'

interface ShiftRow {
  id: number
  user_id: number | null
  status: string
  start_time: string | null
  end_time: string | null
  notes: string | null
}

export default function MyShiftsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { showBackButton } = useTelegramSDK()
  const [filter, setFilter] = useState<Filter>('all')
  const [transferShiftId, setTransferShiftId] = useState<number | null>(null)

  useEffect(() => {
    return showBackButton(() => navigate(-1))
  }, [showBackButton, navigate])

  const { data: shifts = [], isLoading } = useQuery<ShiftRow[]>({
    queryKey: ['twa', 'my-shifts'],
    queryFn: () => twaClient.get('/api/v2/executor/shifts/me', { params: { limit: SHIFTS_LIMIT } }).then(r => r.data),
  })

  const { data: transfers = [] } = useMyTransfers()
  // shift_id, по которым уже есть активная передача → прячем кнопку «Передать».
  const lockedShiftIds = useMemo(
    () => new Set(
      transfers
        .filter((tr) => ACTIVE_TRANSFER_STATUSES.includes(tr.status))
        .map((tr) => tr.shift_id),
    ),
    [transfers],
  )

  const visible = shifts.filter((s: ShiftRow) =>
    filter === 'all' ? true : filter === 'active' ? s.status === 'active' : s.status !== 'active'
  )
  const truncated = shifts.length >= SHIFTS_LIMIT

  const tabs: { key: Filter; label: string }[] = [
    { key: 'all', label: t('twa.exec.myShifts.all') },
    { key: 'active', label: t('twa.exec.myShifts.active') },
    { key: 'completed', label: t('twa.exec.myShifts.completed') },
  ]

  return (
    <div className="p-4 pb-20 min-h-screen bg-gray-50 dark:bg-gray-950">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-emerald-500 text-[13px] mb-3">
        <ArrowLeft size={16} /> {t('common.back')}
      </button>
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">{t('twa.exec.myShifts.title')}</h1>

      <div className="flex gap-2 mb-4">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setFilter(tab.key)}
            className={`px-3 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
              filter === tab.key
                ? 'bg-emerald-500 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-500 border border-gray-200 dark:border-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-center text-gray-400 py-8">{t('common.loading')}</p>}

      {!isLoading && visible.length === 0 && (
        <p className="text-center text-gray-400 py-8 text-[14px]">{t('twa.exec.myShifts.empty')}</p>
      )}

      {visible.map((s: ShiftRow) => {
        const start = s.start_time ? new Date(s.start_time) : null
        const end = s.end_time ? new Date(s.end_time) : null
        const isActive = s.status === 'active'
        const transferable = (s.status === 'active' || s.status === 'planned') && !lockedShiftIds.has(s.id)
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
            {transferable && (
              <button
                onClick={() => setTransferShiftId(s.id)}
                className="w-full mt-2.5 flex items-center justify-center gap-1.5 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 py-2 rounded-xl text-[13px] font-semibold"
              >
                <Repeat size={15} /> {t('twa.exec.transfer.initiate')}
              </button>
            )}
          </div>
        )
      })}

      {truncated && (
        <p className="text-center text-gray-400 py-3 text-[11px]">{t('twa.exec.myShifts.limitNote', { count: SHIFTS_LIMIT })}</p>
      )}

      <TransfersList />

      {transferShiftId !== null && (
        <TransferSheet shiftId={transferShiftId} onClose={() => setTransferShiftId(null)} />
      )}
    </div>
  )
}
