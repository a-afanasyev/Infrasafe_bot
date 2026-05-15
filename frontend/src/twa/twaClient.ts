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
              localStorage.removeItem('twa_refresh_token')
              return ''
            })
            .finally(() => { refreshPromise = null })
        }
        const newToken = await refreshPromise
        if (newToken) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return twaClient(originalRequest)
        }
      }
    }
    return Promise.reject(error)
  }
)
