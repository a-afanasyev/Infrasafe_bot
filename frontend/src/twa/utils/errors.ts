import { toast } from 'sonner'
import { getI18n } from 'react-i18next'
import { apiErrorDetail } from '../../utils/errorMessage'

// Текст по умолчанию — на текущем языке (инстанс, зарегистрированный initReactI18next).
function genericErrorText(): string {
  const i18n = getI18n()
  return i18n?.isInitialized ? i18n.t('twa.errors.generic') : 'Error'
}

/**
 * Extract a human-readable message from an axios/fetch error.
 *
 * Order of preference:
 *   1. FastAPI 422 list of {loc, msg, type} → joined "field: reason; …"
 *   2. FastAPI {detail: string}            → that string
 *   3. fallback                            → caller-provided (по умолчанию — twa.errors.generic)
 *
 * A9-P2-31: err.message НЕ показываем — у axios это английский технический текст
 * («Request failed with status code 500», «Network Error»), и он перекрывал
 * локализованный fallback вызывающего.
 */
export function getErrorMessage(err: unknown, fallback = genericErrorText()): string {
  // A9-P3-20: разбор detail — единый канон utils/errorMessage.apiErrorDetail.
  const detail = apiErrorDetail(err)
  if (detail) return detail
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
