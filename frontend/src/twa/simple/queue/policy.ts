import { apiErrorStatus } from '../../../utils/errorMessage'
import type { FinalReason, QueueItem } from './types'

/** Автоповтор: 5 с → 15 с → 60 с → далее каждые 2 минуты. */
export const RETRY_DELAYS_MS = [5_000, 15_000, 60_000] as const
export const MAX_RETRY_DELAY_MS = 120_000

/** Пауза перед следующей попыткой после `failedAttempts` неудач (≥ 1). */
export function retryDelay(failedAttempts: number): number {
  if (failedAttempts < 1) return 0
  return RETRY_DELAYS_MS[failedAttempts - 1] ?? MAX_RETRY_DELAY_MS
}

export type ErrorClass =
  | { kind: 'retry'; noShift: boolean }
  | { kind: 'final'; reason: FinalReason }

function detailOf(err: unknown): string | null {
  const detail = (err as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail
  return typeof detail === 'string' ? detail : null
}

/**
 * Что делать с ошибкой `POST /complete` (коды — executor_actions.complete_request).
 *
 * Повторять: нет сети, 408/429, 5xx (в т.ч. 503 media_unavailable и 502 от
 * edge без нашего кода), 401 (токен обновится), 403 `no_active_shift` —
 * исполнитель начнёт смену, и та же запись уйдёт без пересъёмки; 409
 * `in_progress` — тот же ключ ещё обрабатывается сервером (параллельный повтор).
 * Окончательно: 404, 409 `invalid_status`, 403 `not_assigned`, 413/415/422,
 * 502 `media_rejected`, прочие 4xx — повтор с теми же байтами ответ не изменит.
 */
export function classifyCompletionError(err: unknown): ErrorClass {
  const status = apiErrorStatus(err)
  const detail = detailOf(err)
  if (status === null || status === 408 || status === 429 || status === 401) {
    return { kind: 'retry', noShift: false }
  }
  if (status === 403) {
    return detail === 'no_active_shift'
      ? { kind: 'retry', noShift: true }
      : { kind: 'final', reason: 'not_yours' }
  }
  if (status === 502 && detail === 'media_rejected') return { kind: 'final', reason: 'bad_photo' }
  if (status >= 500) return { kind: 'retry', noShift: false }
  if (status === 404) return { kind: 'final', reason: 'not_yours' }
  if (status === 409) {
    return detail === 'in_progress' ? { kind: 'retry', noShift: false } : { kind: 'final', reason: 'closed' }
  }
  if (status === 413 || status === 415 || status === 422) return { kind: 'final', reason: 'bad_photo' }
  return { kind: 'final', reason: 'closed' }
}

/** Записи чужих пользователей старше этого срока удаляются. */
export const FOREIGN_TTL_MS = 7 * 24 * 60 * 60 * 1000

/** Запись ждёт автоматической отправки (не провалена окончательно). */
export function isSendable(item: QueueItem): boolean {
  return !item.failed
}

/** По таймеру повторяем только то, что не ждёт смены и не провалено. */
export function isTimerDriven(item: QueueItem): boolean {
  return isSendable(item) && !item.noShift
}

/** Через сколько мс будить очередь (null — будить нечего). */
export function nextWakeDelay(items: readonly QueueItem[], now: number): number | null {
  const timed = items.filter(isTimerDriven)
  if (timed.length === 0) return null
  const earliest = Math.min(...timed.map((i) => i.nextAttemptAt))
  return Math.max(0, earliest - now)
}

/** Записи, которым пора в отправку по таймеру. */
export function dueItems(items: readonly QueueItem[], now: number): QueueItem[] {
  return items.filter((i) => isTimerDriven(i) && i.nextAttemptAt <= now)
}

/** Номера заявок, чьё «Готово» ещё не доставлено (без проваленных). */
export function pendingNumbers(items: readonly QueueItem[]): Set<string> {
  return new Set(items.filter(isSendable).map((i) => i.requestNumber))
}

/** Записи пользователя; чужие — отдельно (на удаление, если старые). */
export function ownItems(items: readonly QueueItem[], userId: number | null): QueueItem[] {
  return userId == null ? [] : items.filter((i) => i.userId === userId)
}

export function staleForeign(items: readonly QueueItem[], userId: number, now: number): QueueItem[] {
  return items.filter((i) => i.userId !== userId && now - i.createdAt > FOREIGN_TTL_MS)
}

/** UUID v4 — ключ идемпотентности. crypto.randomUUID нет в старых WebView. */
export function newIdempotencyKey(): string {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') c.getRandomValues(bytes)
  else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
