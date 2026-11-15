import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Sparkles } from 'lucide-react'
import { PRIMARY_BTN } from '../simple/components/Ui'
import { isCleaningEnabled } from '../../utils/featureFlags'
import { useMyCleaningTasks } from './api'

/**
 * Вход в уборку на экране смены. Виден только тому, у кого сегодня есть задания:
 * остальным (не уборщица, модуль выключен, заданий нет) — пусто.
 */
export default function CleaningEntry({ to }: { to: string }) {
  // Модуль выключен — запроса нет вовсе: экран смены открывает каждый исполнитель.
  return isCleaningEnabled() ? <Entry to={to} /> : null
}

function Entry({ to }: { to: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data } = useMyCleaningTasks()
  if (!data || data.tasks.length === 0) return null
  const left = data.tasks.filter((task) => ['planned', 'in_progress'].includes(task.status)).length
  return (
    <button type="button" onClick={() => navigate(to)} data-testid="cleaning-entry" className={`${PRIMARY_BTN} h-auto min-h-[72px] flex-col gap-0 bg-emerald-700 py-2 text-white`}>
      <span className="flex items-center gap-2"><Sparkles size={28} aria-hidden /> {t('twa.cleaning.entry')}</span>
      <span className="text-[16px] font-medium opacity-90">{t('twa.cleaning.entryLeft', { left, total: data.tasks.length })}</span>
    </button>
  )
}
