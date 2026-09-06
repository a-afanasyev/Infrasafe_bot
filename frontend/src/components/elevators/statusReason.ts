import type { TFunction } from 'i18next'
import { MAX_REASON_LEN } from '../../types/elevators'

/**
 * Причина смены статуса лифта из подсказки после подтверждения заявок.
 * Одна заявка — «подтверждение заявки N»; несколько — первые LISTED_MAX
 * номеров и «+N»; итог жёстко режется до MAX_REASON_LEN (500 на бэке).
 */
export const LISTED_MAX = 5
const ELLIPSIS = '…'

export function buildStatusReason(t: TFunction, requestNumbers: readonly string[]): string {
  const reason =
    requestNumbers.length === 1
      ? t('elevators.prompt.reason', { number: requestNumbers[0] })
      : t('elevators.prompt.reasonMany', {
          count: requestNumbers.length,
          numbers: listNumbers(requestNumbers),
        })
  return clampReason(reason)
}

function listNumbers(numbers: readonly string[]): string {
  const shown = numbers.slice(0, LISTED_MAX).join(', ')
  const rest = numbers.length - LISTED_MAX
  return rest > 0 ? `${shown} +${rest}` : shown
}

function clampReason(reason: string): string {
  if (reason.length <= MAX_REASON_LEN) return reason
  return reason.slice(0, MAX_REASON_LEN - ELLIPSIS.length) + ELLIPSIS
}
