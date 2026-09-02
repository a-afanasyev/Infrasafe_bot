import { useMemo } from 'react'

import { useNameCaseStore } from '../stores/nameCaseStore'
import { formatPersonName, joinPersonName, type NameCase } from '../utils/nameCase'

interface PersonParts {
  first_name?: string | null
  last_name?: string | null
}

export interface PersonNameFormatter {
  mode: NameCase
  /** Серверная строка (executor_name / user_name / author_name / full_name). */
  name: (raw: string | null | undefined, fallback?: string) => string
  /** Объект с first_name/last_name. */
  full: (parts: PersonParts | null | undefined, fallback?: string) => string
}

/**
 * Единая точка отображения имён людей в дашборде с учётом предпочтения
 * «ФИО заглавными». Fallback подставляется ПОСЛЕ форматирования — i18n-строки
 * («Без имени») и `#id` не капсятся. Ссылки стабильны, пока не меняется режим.
 */
export function usePersonName(): PersonNameFormatter {
  const mode = useNameCaseStore(s => s.mode)
  return useMemo<PersonNameFormatter>(
    () => ({
      mode,
      name: (raw, fallback = '') => formatPersonName(raw, mode) || fallback,
      full: (parts, fallback = '') =>
        formatPersonName(joinPersonName(parts?.first_name, parts?.last_name), mode) || fallback,
    }),
    [mode],
  )
}
