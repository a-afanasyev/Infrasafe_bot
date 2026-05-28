/**
 * TWA-specific axios client.
 * Separate from dashboard's apiClient to avoid auth header conflicts.
 * Token is set via TWAContent useEffect.
 * 401 interceptor re-authenticates via refresh token or initData.
 */
import axios, { type InternalAxiosRequestConfig } from 'axios'

// TWA shares the SPA base path (/uk/) — request URLs become /uk/api/...
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

export const twaClient = axios.create({ baseURL: BASE_URL, withCredentials: true })

let refreshPromise: Promise<string> | null = null

twaClient.interceptors.response.use(
  (r) => r,
  async (error) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('twa_refresh_token')
      if (refreshToken) {
        if (!refreshPromise) {
          refreshPromise = axios
            .post(`${BASE_URL}/api/v2/auth/refresh`, { refresh_token: refreshToken })
            .then(({ data }) => {
              localStorage.setItem('twa_refresh_token', data.refresh_token)
              twaClient.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
              return data.access_token as string
            })
            .catch(() => {
              // TWA-06: signal App-level listener so the UI can surface a
              // "session expired" state instead of silently failing every
              // subsequent request with empty Authorization.
              localStorage.removeItem('twa_refresh_token')
              window.dispatchEvent(new CustomEvent('twa:auth-failed'))
              return ''
            })
            .finally(() => { refreshPromise = null })
        }
        const newToken = await refreshPromise
        if (newToken) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          // TWA-24: the retry can still 401 if the freshly-minted access
          // token was already revoked server-side (rotation race / revoke).
          // _retry is set, so the interceptor won't refresh again — escalate
          // to the auth-failed listener so useTWAAuth re-inits instead of
          // leaving the app silently 401ing on every subsequent request.
          try {
            return await twaClient(originalRequest)
          } catch (retryErr: any) {
            if (retryErr?.response?.status === 401) {
              window.dispatchEvent(new CustomEvent('twa:auth-failed'))
            }
            return Promise.reject(retryErr)
          }
        }
      }
    }
    return Promise.reject(error)
  }
)
