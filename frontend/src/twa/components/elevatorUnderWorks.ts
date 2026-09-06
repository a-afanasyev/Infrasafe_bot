/**
 * Р18 в TWA: разбор серверного отказа 409 «по лифту идут работы» и данные для
 * блокирующего блока шага «Лифт».
 *
 * Клиент блокирует «Далее» сам (статус приходит в списке лифтов), но статус
 * может смениться между выбором и отправкой — тогда POST /requests отвечает
 * 409 `{detail: {code: 'elevator_under_works', ...}}`, и мастер показывает тот
 * же текст, а не общий тост (контракт — `api/elevators/errors.py`).
 *
 * Вынесено из компонентов: react-refresh требует «только компоненты» в .tsx.
 */
import type { ElevatorStatus } from '../../types/elevators'

export const UNDER_WORKS_CODE = 'elevator_under_works'

export interface ElevatorUnderWorks {
  status: ElevatorStatus | null
  /** ISO-8601 или null, если момент смены статуса неизвестен. */
  statusSince: string | null
  label: string
}

/** Ошибка axios → данные отказа Р18; любая другая ошибка → null. */
export function parseUnderWorksError(error: unknown): ElevatorUnderWorks | null {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  if (response?.status !== 409) return null
  const detail = response.data?.detail
  if (typeof detail !== 'object' || detail === null) return null
  const body = detail as Record<string, unknown>
  if (body.code !== UNDER_WORKS_CODE) return null
  return {
    status: typeof body.status === 'string' ? (body.status as ElevatorStatus) : null,
    statusSince: typeof body.status_since === 'string' ? body.status_since : null,
    label: typeof body.label === 'string' ? body.label : '',
  }
}

/** «01.09.2026 12:30» в локали браузера; без момента — null (текст без «с …»). */
export function formatStatusSince(iso: string | null | undefined): string | null {
  if (!iso) return null
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleString()
}

/**
 * `tel:`-цель из произвольной строки телефона — как в публичном виджете
 * (`ResidentElevatorsPage`): оставляем только цифры и «+».
 */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}
