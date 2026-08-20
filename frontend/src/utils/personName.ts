/**
 * ФИО одной строкой — клиентское зеркало канона бэкенда.
 *
 * Источник истины — `uk_management_bot/utils/person_name.py`; здесь ровно
 * столько, чтобы менеджер увидел ошибку до сетевого запроса, а не 422 после.
 * Расхождение лимита пинится тестом
 * `tests/services/test_person_name_limit_ssot.py`: UI, разрешающий больше
 * бэкенда, отдаёт пользователю форму, которую нельзя отправить.
 */

/** Совпадает с `MAX_FULL_NAME_LEN` в person_name.py. */
export const MAX_FULL_NAME_LEN = 200

/** Схлопнуть пробельное и обрезать края (невидимое чистит бэкенд). */
export function normalizeFullName(raw: string): string {
  return raw.replace(/\s+/g, ' ').trim()
}

export type FullNameError = 'empty' | 'noLetters' | 'tooLong' | null

/** Повод отказа либо null. Порядок проверок — как в `validate_full_name`. */
export function validateFullName(raw: string): FullNameError {
  const value = normalizeFullName(raw)
  if (!value) return 'empty'
  if (value.length > MAX_FULL_NAME_LEN) return 'tooLong'
  // \p{L} вместо [A-Za-zА-Яа-я]: узбекская латиница с диакритикой и кириллица
  // должны проходить одинаково.
  if (!/\p{L}/u.test(value)) return 'noLetters'
  return null
}
