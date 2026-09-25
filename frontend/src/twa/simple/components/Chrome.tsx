import { useLocation, useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ClipboardList, Clock, Hand, WifiOff } from 'lucide-react'
import { useTelegramSDK } from '../../hooks/useTelegramSDK'
import { useCurrentShift } from '../api'
import { useElapsed, useOnline } from '../hooks/useSimpleNav'
import { useCompletionQueue } from '../queue/CompletionQueue'

/** Нет связи — жёлтая полоса; фото в очереди — счётчик (цвет + иконка + число). */
export function ConnectionBar() {
  const { t } = useTranslation()
  const online = useOnline()
  const { pendingCount } = useCompletionQueue()
  if (online && pendingCount === 0) return null
  return (
    <div
      role="status"
      className={`sticky top-0 z-40 flex items-center justify-center gap-4 px-4 py-3 text-[18px] font-semibold ${
        online ? 'bg-gray-200 text-gray-800 dark:bg-gray-800 dark:text-gray-100' : 'bg-yellow-300 text-gray-900'
      }`}
    >
      {!online && (
        <span className="inline-flex items-center gap-2">
          <WifiOff size={22} aria-hidden /> {t('twa.simple.offline')}
        </span>
      )}
      {pendingCount > 0 && (
        <span className="inline-flex items-center gap-2">
          <Clock size={22} aria-hidden /> {t('twa.simple.pendingPhotos', { count: pendingCount })}
        </span>
      )}
    </div>
  )
}

/** Плашка смены над вкладками; тап — экран смены. */
export function ShiftBanner() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data: shift, isLoading, isError } = useCurrentShift()
  const elapsed = useElapsed(shift?.start_time)
  if (isLoading) return null
  // Состояние смены неизвестно (ошибка без данных) — нейтрально «Смена»,
  // а не «Смена не начата»: неверная подсказка хуже никакой.
  const unknown = isError && shift === undefined
  const on = !!shift?.id
  return (
    <button
      type="button"
      onClick={() => navigate('/twa/s/shift')}
      className={`w-full h-[56px] flex items-center justify-center gap-3 text-[18px] font-semibold ${
        on && !unknown
          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200'
          : 'bg-gray-200 text-gray-800 dark:bg-gray-800 dark:text-gray-200'
      }`}
    >
      <Clock size={24} aria-hidden />
      {unknown ? t('twa.simple.shift.title') : on ? `${t('twa.simple.shift.on')} ${elapsed}` : t('twa.simple.shift.off')}
    </button>
  )
}

const TABS = [
  { path: '/twa/s', icon: ClipboardList, key: 'twa.simple.tabs.mine' },
  { path: '/twa/s/pool', icon: Hand, key: 'twa.simple.tabs.pool' },
] as const

/** Две крупные вкладки «Мои» / «Взять» (иконка + слово) и плашка смены над ними. */
export function SimpleTabs() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { haptic } = useTelegramSDK()
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 pb-[env(safe-area-inset-bottom)]">
      <ShiftBanner />
      <div className="grid grid-cols-2">
        {TABS.map(({ path, icon: Icon, key }) => {
          const active = pathname === path
          return (
            <button
              key={path}
              type="button"
              aria-current={active ? 'page' : undefined}
              onClick={() => {
                haptic('selection')
                navigate(path)
              }}
              className={`h-[72px] flex flex-col items-center justify-center gap-1 text-[18px] font-bold ${
                active ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-500 dark:text-gray-400'
              }`}
            >
              <Icon size={30} aria-hidden />
              {t(key)}
            </button>
          )
        })}
      </div>
    </nav>
  )
}
