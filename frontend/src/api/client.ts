import axios, { type InternalAxiosRequestConfig } from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

export const apiClient = axios.create({ baseURL: BASE_URL, withCredentials: true })

let refreshPromise: Promise<string> | null = null

apiClient.interceptors.request.use((config) => {
  // Keep Authorization header for TWA backward compat; browser flow uses httpOnly cookies
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  (r) => r,
  async (error) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        if (!refreshPromise) {
          refreshPromise = axios
            .post(`${BASE_URL}/api/v2/auth/refresh`, { refresh_token: refreshToken }, { withCredentials: true })
            .then(({ data }) => {
              localStorage.setItem('refresh_token', data.refresh_token)
              // access_token is now set via httpOnly cookie by the server
              return data.access_token as string
            })
            .catch((err) => {
              localStorage.removeItem('access_token')
              localStorage.removeItem('refresh_token')
              window.location.href = '/login'
              throw err
            })
            .finally(() => { refreshPromise = null })
        }

        try {
          await refreshPromise
          // Cookie is set by the server; just retry the original request
          return apiClient(originalRequest)
        } catch (refreshError) {
          return Promise.reject(refreshError)
        }
      }
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
