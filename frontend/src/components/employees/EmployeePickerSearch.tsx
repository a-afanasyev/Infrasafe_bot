import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'

interface Props {
  value: string
  onChange: (value: string) => void
  /** Сколько записей показано и сколько всего под фильтрами — для подсказки «уточните поиск». */
  shown: number
  total: number
  className?: string
}

/**
 * Поле поиска над списком/селектом сотрудников (AUD7-CODE-06). Поиск серверный
 * (см. `useEmployeePicker`); при усечённой выдаче подсказывает уточнить запрос.
 */
export default function EmployeePickerSearch({ value, onChange, shown, total, className }: Props) {
  const { t } = useTranslation()
  return (
    <div className={className}>
      <Input
        type="search"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={t('employees.searchPlaceholder')}
        aria-label={t('employees.searchPlaceholder')}
      />
      {total > shown && (
        <p className="m-0 mt-1 text-[11px] text-text-muted">
          {t('employees.pickerTruncated', { shown, total })}
        </p>
      )}
    </div>
  )
}
