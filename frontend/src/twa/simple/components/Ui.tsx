import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Check, Hourglass, RotateCcw, X } from 'lucide-react'

// Размеры простого режима: главная кнопка 72 px во всю ширину, вторичные
// ≥ 56 px, текст ≥ 18 px. Держим классы в одном месте.
export const PRIMARY_BTN =
  'w-full h-[72px] rounded-2xl text-[22px] font-bold flex items-center justify-center gap-3 disabled:opacity-60 active:scale-[0.98] transition-transform'
export const SECONDARY_BTN =
  'w-full h-[56px] rounded-2xl text-[20px] font-semibold flex items-center justify-center gap-2 disabled:opacity-60 active:scale-[0.98] transition-transform'

/** Ошибка загрузки: знак + «Ещё раз». Никогда не «нет заданий». */
export function ErrorBlock({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="flex flex-col items-center gap-4 py-12 px-4 text-center">
      <AlertTriangle size={64} className="text-amber-500" aria-hidden />
      <p className="text-[20px] font-semibold text-gray-800 dark:text-gray-100">{t('twa.simple.error.load')}</p>
      <button type="button" onClick={onRetry} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
        <RotateCcw size={28} aria-hidden /> {t('twa.simple.error.retry')}
      </button>
    </div>
  )
}

export function Loading() {
  return (
    <ul className="flex flex-col gap-3" aria-busy="true">
      {[0, 1, 2].map((i) => (
        <li key={i} className="list-none h-[120px] rounded-2xl bg-gray-200 dark:bg-gray-800 animate-pulse" />
      ))}
    </ul>
  )
}

/** Серая плашка вместо «Готово»: закрыть заявку сейчас нельзя, решает менеджер. */
export function WaitManagerPlate() {
  const { t } = useTranslation()
  return (
    <div
      role="status"
      className="w-full h-[72px] rounded-2xl bg-gray-300 dark:bg-gray-700 text-gray-800 dark:text-gray-100 text-[22px] font-bold flex items-center justify-center gap-3"
    >
      <Hourglass size={30} aria-hidden /> {t('twa.simple.waitManager')}
    </div>
  )
}

interface ResultProps {
  ok: boolean
  title: string
  subtitle?: string
  children?: ReactNode
}

/** Исход на весь экран: зелёная галка или красный крест. */
export function ResultScreen({ ok, title, subtitle, children }: ResultProps) {
  return (
    <div
      role={ok ? 'status' : 'alert'}
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 p-6 text-center ${
        ok ? 'bg-emerald-600' : 'bg-red-600'
      } text-white`}
    >
      <div className="w-40 h-40 rounded-full bg-white/20 flex items-center justify-center">
        {ok ? <Check size={112} strokeWidth={3} aria-hidden /> : <X size={112} strokeWidth={3} aria-hidden />}
      </div>
      <p className="text-[28px] font-bold">{title}</p>
      {subtitle && <p className="text-[20px]">{subtitle}</p>}
      {children && <div className="w-full max-w-md flex flex-col gap-3">{children}</div>}
    </div>
  )
}

interface ConfirmProps {
  title: string
  children?: ReactNode
  onYes: () => void
  onNo: () => void
  busy?: boolean
}

/** Подтверждение «Да / Нет» — две кнопки по 72 px. */
export function ConfirmSheet({ title, children, onYes, onNo, busy }: ConfirmProps) {
  const { t } = useTranslation()
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end" onClick={onNo}>
      <div
        role="dialog"
        aria-label={title}
        className="w-full bg-white dark:bg-gray-900 rounded-t-3xl p-4 pb-[calc(16px+env(safe-area-inset-bottom))] flex flex-col gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-[24px] font-bold text-center text-gray-900 dark:text-gray-50">{title}</p>
        {children}
        <div className="grid grid-cols-2 gap-3">
          <button type="button" onClick={onNo} disabled={busy} className={`${PRIMARY_BTN} bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-50`}>
            <X size={28} aria-hidden /> {t('twa.simple.no')}
          </button>
          <button type="button" onClick={onYes} disabled={busy} className={`${PRIMARY_BTN} bg-emerald-600 text-white`}>
            <Check size={28} aria-hidden /> {t('twa.simple.yes')}
          </button>
        </div>
      </div>
    </div>
  )
}
