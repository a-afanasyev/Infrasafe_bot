import { toast } from 'sonner'

import { apiErrorDetail } from '../../utils/errorMessage'

/**
 * Extract a human-readable message from an axios/fetch error.
 *
 * Order of preference:
 *   1. FastAPI 422 list of {loc, msg, type} → joined "field: reason; …"
 *   2. FastAPI {detail: string}            → that string
 *   3. axios err.message                   → e.g. "Network Error"
 *   4. fallback                            → caller-provided
 */
export function getErrorMessage(err: unknown, fallback = 'Произошла ошибка'): string {
  // A9-P3-20: разбор detail — единый канон utils/errorMessage.apiErrorDetail.
  const detail = apiErrorDetail(err)
  if (detail) return detail

  const message = (err as { message?: unknown } | null)?.message
  if (typeof message === 'string' && message) return message

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
