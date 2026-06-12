// FE-04: Telegram Login Widget вызывает window.onTelegramAuth с внешним
// неконтролируемым payload'ом. До POST'а на бэкенд проверяем обязательные
// поля контракта виджета (id + hash) — мусорный/подделанный вызов не должен
// уходить на /auth/telegram-widget.

export interface TelegramAuthPayload {
  id: number
  hash: string
  auth_date?: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
}

export function isValidTelegramAuth(payload: unknown): payload is TelegramAuthPayload {
  if (typeof payload !== 'object' || payload === null) return false
  const obj = payload as Record<string, unknown>
  return (
    typeof obj.id === 'number' &&
    Number.isFinite(obj.id) &&
    typeof obj.hash === 'string' &&
    obj.hash.length > 0
  )
}
