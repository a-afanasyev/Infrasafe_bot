import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useSetEmployeeLanguage,
  useToggleSimpleMode,
  type EmployeeLanguage,
} from '../../hooks/useEmployees'
import { Select } from '@/components/ui/select'
import { cn } from '@/lib/utils'

const LANGUAGES: readonly EmployeeLanguage[] = ['ru', 'uz', 'uz_cyrl']

interface Props {
  employeeId: number
  simpleMode: boolean
  language: string
}

/**
 * Простой режим исполнителя + язык бота/Mini App — настраивает менеджер из
 * карточки сотрудника. Без оптимизма: переключатель ждёт ответа бэка
 * (disabled на время запроса), состояние приходит из перезапроса карточки.
 */
export default function SimpleModeSection({ employeeId, simpleMode, language }: Props) {
  const { t } = useTranslation()
  const toggle = useToggleSimpleMode(employeeId)
  const setLanguage = useSetEmployeeLanguage(employeeId)
  const titleId = useId()
  const languageId = useId()

  return (
    <div className="bg-bg-card border border-border-default rounded-default p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div id={titleId} className="text-[13px] font-semibold text-text-primary">
            {t('employeeDetail.simpleMode.title')}
          </div>
          <div className="text-[11px] text-text-muted mt-0.5">
            {t('employeeDetail.simpleMode.hint')}
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={simpleMode}
          aria-labelledby={titleId}
          disabled={toggle.isPending}
          onClick={() => toggle.mutate(!simpleMode)}
          className={cn(
            'relative shrink-0 inline-flex h-6 w-11 items-center rounded-full border border-border-default transition-colors',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50',
            simpleMode ? 'bg-accent' : 'bg-bg-surface',
          )}
        >
          <span
            className={cn(
              'inline-block h-4 w-4 rounded-full bg-white shadow transition-transform',
              simpleMode ? 'translate-x-6' : 'translate-x-1',
            )}
          />
        </button>
      </div>

      <div className="flex items-center justify-between gap-4">
        <label htmlFor={languageId} className="text-[13px] text-text-primary">
          {t('employeeDetail.simpleMode.language')}
        </label>
        <Select
          id={languageId}
          value={language}
          disabled={setLanguage.isPending}
          onChange={e => setLanguage.mutate(e.target.value as EmployeeLanguage)}
          className="w-auto min-w-[200px]"
        >
          {LANGUAGES.map(code => (
            <option key={code} value={code}>
              {t(`employeeDetail.simpleMode.languages.${code}`)}
            </option>
          ))}
        </Select>
      </div>
    </div>
  )
}
