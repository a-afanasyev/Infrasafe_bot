import { toast } from 'sonner'
import { getI18n } from 'react-i18next'
import axios from 'axios'
import { apiErrorStatus } from '../../utils/errorMessage'

// Текст по умолчанию — на текущем языке (инстанс, зарегистрированный initReactI18next).
function genericErrorText(): string {
  const i18n = getI18n()
  return i18n?.isInitialized ? i18n.t('twa.errors.generic') : 'Error'
}

// Статусы, для которых общий текст полезнее контекстного fallback вызывающего:
// они говорят пользователю, ЧТО делать (проверить сеть, подождать, повторить).
function statusErrorKey(err: unknown): string | null {
  if (!axios.isAxiosError(err)) return null
  const status = apiErrorStatus(err)
  if (status === null || status === 408) return 'twa.errors.network'
  if (status === 403) return 'twa.errors.forbidden'
  if (status === 413) return 'twa.errors.tooLarge'
  if (status === 429) return 'twa.errors.tooMany'
  if (status >= 500) return 'twa.errors.server'
  return null
}

/**
 * Локализованный текст ошибки для пользователя TWA.
 *
 *   1. Сеть/408, 403, 413, 429, 5xx → общий текст по статусу (twa.errors.*)
 *   2. иначе                          → fallback вызывающего (по умолчанию — twa.errors.generic)
 *
 * Сырой `detail` ответа НЕ показываем: это технический текст бэкенда, чаще
 * всего на английском («Transition not allowed», «description: too short»).
 * err.message (A9-P2-31) — тоже нет. Машинный код ошибки, если он нужен для
 * ветвления, читать через utils/errorMessage (apiErrorCode/apiErrorDetail).
 * Дашборд этим не пользуется — у него свой safeErrorMessage с detail.
 */
export function getErrorMessage(err: unknown, fallback = genericErrorText()): string {
  const key = statusErrorKey(err)
  const i18n = getI18n()
  if (key && i18n?.isInitialized) return i18n.t(key)
  return fallback
}

/**
 * Show an error toast — unless we're offline.
 *
 * TWA-28: when `navigator.onLine === false` the persistent OfflineIndicator
 * banner already tells the user there's no connection. Firing a "Network
 * Error" toast on top of it (and one more per failed tap) is double noise,
 * so we suppress the toast and let the banner speak.
 */
export function notifyError(err: unknown, fallback?: string): void {
  if (typeof navigator !== 'undefined' && !navigator.onLine) return
  toast.error(getErrorMessage(err, fallback))
}
