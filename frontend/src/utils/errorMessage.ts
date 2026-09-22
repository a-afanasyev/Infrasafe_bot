import axios from 'axios'

/**
 * A9-P3-20: ЕДИНЫЙ разбор `detail` ответа API (дашборд, TWA — twa/utils/errors.ts
 * делегирует сюда). Раньше было три копии, и они уже разошлись.
 *
 *   1. FastAPI 422 — список {loc, msg} → «field: reason; …»
 *   2. {detail: string}                → строка
 *   3. {detail: {code, message}}       → message (машинный код — apiErrorCode)
 *
 * Возвращает null, если человекочитаемого detail нет. Никогда не отдаёт
 * объект/массив: сырой detail в JSX ронял рендер («Objects are not valid as a
 * React child»).
 */
export function apiErrorDetail(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)
    ?.response?.data?.detail

  if (Array.isArray(detail)) {
    const joined = detail
      .map((d: { loc?: unknown; msg?: unknown }) => {
        const msg = typeof d?.msg === 'string' ? d.msg : ''
        const path = Array.isArray(d?.loc) ? d.loc.filter((p) => p !== 'body').join('.') : ''
        return path && msg ? `${path}: ${msg}` : msg
      })
      .filter(Boolean)
      .join('; ')
    return joined || null
  }
  if (typeof detail === 'string') return detail.trim() ? detail : null
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    return typeof message === 'string' && message.trim() ? message : null
  }
  return null
}

/**
 * Машинный код ошибки — для ветвления UI вместо regex по тексту (правка
 * формулировки на бэке ломала ветвление). Источники: заголовок `X-Error-Code`
 * (регистрация: detail остаётся строкой ради обратной совместимости) или
 * `detail: {code, message}`.
 */
export function apiErrorCode(error: unknown): string | null {
  const response = (error as {
    response?: { headers?: Record<string, unknown>; data?: { detail?: unknown } }
  } | null)?.response
  const header = response?.headers?.['x-error-code']
  if (typeof header === 'string' && header) return header
  const detail = response?.data?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const code = (detail as { code?: unknown }).code
    return typeof code === 'string' && code ? code : null
  }
  return null
}

/** HTTP-статус ответа-ошибки (axios-подобной), либо null. */
export function apiErrorStatus(error: unknown): number | null {
  const status = (error as { response?: { status?: unknown } } | null)?.response?.status
  return typeof status === 'number' ? status : null
}

/**
 * Безопасный текст ошибки для UI: короткий detail API или fallback. Длинные
 * payload'ы (≥200) и не-axios ошибки → fallback.
 */
export function safeErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = apiErrorDetail(error)
    if (detail && detail.length < 200) {
      return detail
    }
  }
  return fallback
}

/**
 * Ответ-отказ по данным (400/404/409/422) против недоступности сервиса: без этого
 * различия «неверный лицевой счёт» показывался как «сервис недоступен».
 */
export function isValidationError(error: unknown): boolean {
  return axios.isAxiosError(error) && [400, 404, 409, 422].includes(error.response?.status ?? 0)
}
