import { useTranslation } from 'react-i18next'
import { useEmployees } from '../../hooks/useEmployees'
import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'

/** Кого выбрали: конкретный человек, «дежурный» либо ничего. */
export type ExecutorChoice = number | 'duty' | ''

interface Props {
  value: ExecutorChoice
  onChange: (value: ExecutorChoice) => void
  /** Кого не показывать. Нужен переназначению: текущий исполнитель в списке —
   *  это выбор «оставить как есть», который сервер отклонит как повтор. */
  excludeId?: number | null
  /** Категория заявки: сервер оставит только исполнителей, чья специализация
   *  её покрывает (канон-предикат бота, джокер `universal`). Без неё список —
   *  все verified-исполнители. */
  forCategory?: string | null
  /** Показывать ли вариант «дежурному». */
  showDuty?: boolean
  label?: string
  /** Что написать, когда показывать некого (обычно: подходящий был один и это
   *  текущий исполнитель). Пустой список без объяснения читается как поломка. */
  emptyText?: string
}

/**
 * Выбор исполнителя — общий для взятия заявки в работу и для переназначения.
 *
 * Извлечён из `TransitionModal`, где жил инлайном: второй копией он разъехался
 * бы с первой (индикатор смены, порядок, стили), а решение «кого показывать»
 * обязано быть одно на оба флоу.
 */
export default function ExecutorPicker({
  value,
  onChange,
  excludeId = null,
  forCategory = null,
  showDuty = true,
  label,
  emptyText,
}: Props) {
  const { t } = useTranslation()
  const { data: employees = [] } = useEmployees({
    verification_status: 'verified',
    ...(forCategory ? { for_category: forCategory } : {}),
  })

  const candidates = employees.filter(emp => emp.id !== excludeId)

  return (
    <div className="space-y-2">
      <Label className="text-text-secondary">{label ?? t('kanban.selectExecutorLabel')}</Label>

      {showDuty && (
        <>
          <button
            type="button"
            onClick={() => onChange('duty')}
            className={cn(
              'w-full text-left border rounded-default p-3 text-sm transition-colors',
              value === 'duty'
                ? 'border-accent bg-accent-dim text-accent'
                : 'border-border-default hover:bg-bg-surface text-text-primary'
            )}
          >
            <span className="font-medium">{t('kanban.dutyOfficer')}</span>
            <span className="text-text-muted text-xs ml-2">{t('kanban.assignToDuty')}</span>
          </button>
          <div className="text-xs text-text-muted text-center py-1">
            {t('kanban.orSpecificSpecialist')}
          </div>
        </>
      )}

      {candidates.length === 0 ? (
        <p className="text-xs text-text-muted text-center py-3 m-0">
          {emptyText ?? t('kanban.noExecutorsAvailable')}
        </p>
      ) : (
        <div className="max-h-48 overflow-y-auto space-y-1">
          {candidates.map(emp => {
            const name =
              [emp.first_name, emp.last_name].filter(Boolean).join(' ') || `#${emp.id}`
            return (
              <button
                type="button"
                key={emp.id}
                onClick={() => onChange(emp.id)}
                className={cn(
                  'w-full text-left border rounded-default p-3 text-sm transition-colors',
                  value === emp.id
                    ? 'border-accent bg-accent-dim text-accent'
                    : 'border-border-default hover:bg-bg-surface text-text-primary'
                )}
              >
                <span className="font-medium">{name}</span>
                {emp.active_shift_id !== null && (
                  <span className="ml-2 text-xs text-emerald">● {t('kanban.onShift')}</span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
