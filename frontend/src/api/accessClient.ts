import axios from 'axios'

import { refreshSession } from './client'

/**
 * HTTP-клиент домена контроля доступа (`uk-access-api`).
 *
 * Отдельный инстанс от основного `apiClient` (api/client.ts): у access-API свой
 * baseURL и своя модель авторизации в dev. Перехватчик ошибок упрощён (без
 * cookie-refresh-флоу основного UK-API) — read-only реестр + действия охраны.
 *
 * ── Авторизация — два пути (как у WS-ленты, см. useAccessSecurityFeed) ────────
 *
 *  (а) PROD, same-origin за edge: access-API проксируется тем же origin, что и
 *      SPA. Браузер сам прикладывает httpOnly cookie web-сессии (`uk_access`) —
 *      `withCredentials: true`. JS токен не читает и не должен. Это путь по
 *      умолчанию: baseURL = same-origin путь `${BASE_URL}api/v1/access`.
 *
 *  (б) DEV / cookieless: в dev SPA (:3002) и access-API (:8086) живут на РАЗНЫХ
 *      портах → cross-origin cookie не уходит. Тогда клиент шлёт JWT в заголовке
 *      `Authorization: Bearer <jwt>`. Бэкенд это принимает: get_current_user
 *      (uk_management_bot/api/dependencies.py) сначала пробует cookie, затем
 *      Authorization-заголовок. Токен НИКОГДА не логируется.
 *
 * Конфигурация (env):
 *  - `VITE_ACCESS_API_URL` — базовый URL access-API. По умолчанию same-origin
 *    путь `${BASE_URL}api/v1/access` (прод за edge).
 *  - `VITE_ACCESS_API_DEV_TOKEN` ИЛИ sessionStorage['access_api_dev_token'] —
 *    dev-JWT. Если задан, шлётся в заголовке Authorization (путь «б»). Иначе
 *    клиент полагается на cookie (путь «а», прод).
 */

// Ключ sessionStorage для dev-JWT (cookieless-путь). Per-tab, как у WS-ленты.
export const ACCESS_API_DEV_TOKEN_KEY = 'access_api_dev_token'

/** Same-origin базовый путь access-API под BASE_URL дашборда (прод за edge). */
function defaultBaseUrl(): string {
  // BASE_URL уже со слешем на конце (напр. "/uk/"); вычищаем дубль слешей.
  return `${import.meta.env.BASE_URL}api/v1/access`.replace(/\/{2,}/g, '/')
}

const BASE_URL = import.meta.env.VITE_ACCESS_API_URL ?? defaultBaseUrl()

/** dev-токен из env или sessionStorage (если задан → cookieless-путь). */
function resolveDevToken(): string | null {
  const fromEnv = import.meta.env.VITE_ACCESS_API_DEV_TOKEN
  if (fromEnv) return fromEnv
  try {
    return sessionStorage.getItem(ACCESS_API_DEV_TOKEN_KEY)
  } catch {
    return null
  }
}

export const accessClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // прод: httpOnly cookie web-сессии уходит на same-origin
})

// dev-bearer: при наличии токена прикладываем Authorization к каждому запросу.
// В проде токена нет → полагаемся на cookie (путь «а»). Токен не логируется.
accessClient.interceptors.request.use((config) => {
  const devToken = resolveDevToken()
  if (devToken) {
    config.headers.set('Authorization', `Bearer ${devToken}`)
  }
  return config
})

// 401 на cookie-пути (прод, путь «а»): web-сессия (uk_access) истекла по TTL,
// пока охрана не дёргала основной UK-API. Переиспользуем общий cookie-refresh
// (он ставит свежий uk_access) и повторяем запрос один раз — экран охраны не
// валится в «Ошибка» до перезагрузки. В dev cookieless-пути (есть devToken)
// cookie-refresh не поможет → пропускаем, оставляя прежнее поведение.
accessClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as (typeof error.config) & { _retry?: boolean }
    const isAuthError = error.response?.status === 401
    if (isAuthError && originalRequest && !originalRequest._retry && !resolveDevToken()) {
      originalRequest._retry = true
      try {
        await refreshSession()
        return accessClient(originalRequest)
      } catch (refreshError) {
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  },
)
