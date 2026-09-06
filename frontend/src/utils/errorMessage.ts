import axios from 'axios'

export function safeErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail.length < 200) {
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
