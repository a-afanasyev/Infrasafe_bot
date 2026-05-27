import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { useTelegramSDK } from './useTelegramSDK'

// TWA shares the SPA base path (/uk/) — request URLs become /uk/api/...
const BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.BASE_URL.replace(/\/$/, '')

export function useTWAAuth() {
  const { initData } = useTelegramSDK()
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const authenticate = useCallback(async () => {
    try {
      if (!initData) {
        // Try refresh token from localStorage
        const refreshToken = localStorage.getItem('twa_refresh_token')
        if (refreshToken) {
          try {
            const { data } = await axios.post(`${BASE_URL}/api/v2/auth/refresh`, { refresh_token: refreshToken })
            setAccessToken(data.access_token)
            localStorage.setItem('twa_refresh_token', data.refresh_token)
            return
          } catch {
            localStorage.removeItem('twa_refresh_token')
          }
        }
        return
      }

      const { data } = await axios.post(`${BASE_URL}/api/v2/auth/twa`, { init_data: initData })
      setAccessToken(data.access_token)
      localStorage.setItem('twa_refresh_token', data.refresh_token)
    } catch (err) {
      console.error('TWA auth failed:', err)
    } finally {
      setIsLoading(false)
    }
  }, [initData])

  useEffect(() => {
    // TWA-05: don't re-authenticate if we already have a token — useTelegramSDK
    // updates `initData` once the Telegram script finishes loading, which
    // would otherwise re-fire authenticate() after a successful first attempt.
    if (accessToken) return
    authenticate()
  }, [authenticate, accessToken])

  // TWA-06: clear local token state when the axios interceptor reports that
  // refresh failed. Without this the UI keeps treating the user as
  // authenticated while every subsequent request fails with 401.
  useEffect(() => {
    const onAuthFailed = () => setAccessToken(null)
    window.addEventListener('twa:auth-failed', onAuthFailed)
    return () => window.removeEventListener('twa:auth-failed', onAuthFailed)
  }, [])

  return { accessToken, isLoading, isAuthenticated: !!accessToken }
}
