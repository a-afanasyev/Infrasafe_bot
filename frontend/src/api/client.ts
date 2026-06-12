import axios from 'axios'

// All UK API requests are relative to the SPA base path (e.g. /uk/api/...).
// VITE_API_URL still wins for tests / dev with a non-default backend.
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

// Login route lives at <base>login (e.g. /uk/login).
const LOGIN_URL = `${import.meta.env.BASE_URL}login`

export const apiClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // sends uk_access / uk_refresh cookies on Path=/uk/
})

// FE-047: клиент БЕЗ 401-interceptor — для auth-эндпоинтов страницы логина.
// apiClient на 401 пытается refresh → при неудаче редиректит на /login,
// что на самой странице логина перезагружало её и стирало inline-ошибку
// («неверный пароль» выглядел как молчаливый сброс формы).
export const publicClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // login/verify-otp ставят auth-cookies в ответе
})

let refreshPromise: Promise<void> | null = null

apiClient.interceptors.response.use(
  (r) => r,
  async (error) => {
    const originalRequest = error.config as (typeof error.config) & { _retry?: boolean }
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      // Cookie-based refresh — server reads uk_refresh from httpOnly cookie,
      // sets a fresh uk_access cookie in the response. No body, no token plumbing.
      if (!refreshPromise) {
        refreshPromise = axios
          .post(`${BASE_URL}/api/v2/auth/refresh`, undefined, { withCredentials: true })
          .then(() => undefined)
          .catch((err) => {
            window.location.href = LOGIN_URL
            throw err
          })
          .finally(() => { refreshPromise = null })
      }

      try {
        await refreshPromise
        return apiClient(originalRequest)
      } catch (refreshError) {
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  }
)
