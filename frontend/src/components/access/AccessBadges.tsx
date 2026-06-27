import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

/**
 * Цветные бейджи и форматтеры домена контроля доступа (в стиле статус-бейджей
 * проекта). Переводы через i18n с фолбэком на сырой ключ — словарь может
 * отставать от бэкенда, но оператор всё равно видит исход.
 */

// Цвет бейджа решения (allow/deny/manual_review + дефолт).
const DECISION_CLASS: Record<string, string> = {
  allow: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  deny: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  manual_review: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
}
const FALLBACK_CLASS = 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'

// Цвет бейджа статуса (ТС/пропуск/заявка): зелёные — активно, красные —
// заблокировано/отклонено, янтарь — ожидание, серый — прочее.
const STATUS_CLASS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  allowed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  approved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  blocked: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  denied: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  rejected: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  revoked: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  expired: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  inactive: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  pending_review: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
}

// Цвет бейджа типа парковочной зоны: общая (shared) — акцент, закреплённая
// (assigned) — нейтральный.
const PARKING_TYPE_CLASS: Record<string, string> = {
  assigned: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300',
  shared: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',
}

const PILL = 'inline-block rounded-full px-2.5 py-0.5 text-[12px] font-medium whitespace-nowrap'

export function DecisionBadge({ decision }: { decision: string | null }) {
  const { t } = useTranslation()
  if (!decision) return <span className="text-text-muted">—</span>
  const label = t(`accessControl.decision.${decision}`, { defaultValue: decision })
  return <span className={cn(PILL, DECISION_CLASS[decision] ?? FALLBACK_CLASS)}>{label}</span>
}

export function AccessStatusBadge({ status }: { status: string | null }) {
  const { t } = useTranslation()
  if (!status) return <span className="text-text-muted">—</span>
  const label = t(`accessControl.status.${status}`, { defaultValue: status })
  return <span className={cn(PILL, STATUS_CLASS[status] ?? FALLBACK_CLASS)}>{label}</span>
}

/** Бейдж типа парковочной зоны (assigned/shared). */
export function ParkingTypeBadge({ type }: { type: string | null }) {
  const { t } = useTranslation()
  if (!type) return <span className="text-text-muted">—</span>
  const label = t(`accessControl.parking.parkingType.${type}`, { defaultValue: type })
  return <span className={cn(PILL, PARKING_TYPE_CLASS[type] ?? FALLBACK_CLASS)}>{label}</span>
}
