import { toast } from 'sonner'
import { getI18n } from 'react-i18next'

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
 *   3. axios err.message                   → e.g. "Network Error"
 *   4. fallback                            → caller-provided (по умолчанию — twa.errors.generic)
 */
export function getErrorMessage(err: unknown, fallback = genericErrorText()): string {
  const anyErr = err as {
    response?: { data?: { detail?: unknown } }
    message?: string
  }

  const detail = anyErr?.response?.data?.detail

  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const path = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : ''
        return path ? `${path}: ${d.msg ?? ''}` : (d.msg ?? '')
      })
      .filter(Boolean)
      .join('; ')
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (anyErr?.message) {
    return anyErr.message
  }

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
