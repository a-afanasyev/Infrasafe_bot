import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { useTelegramSDK } from './useTelegramSDK'
import { getTwaRefreshToken, setTwaRefreshToken, clearTwaRefreshToken } from '../twaToken'

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
        // No fresh initData yet — try the in-memory refresh token (survives
        // within the session, not across reload). On reload this is null and
        // we wait for initData (useTelegramSDK repopulates it on open).
        const refreshToken = getTwaRefreshToken()
        if (refreshToken) {
          try {
            const { data } = await axios.post(`${BASE_URL}/api/v2/auth/refresh`, { refresh_token: refreshToken })
            setAccessToken(data.access_token)
            setTwaRefreshToken(data.refresh_token)
            return
          } catch {
            clearTwaRefreshToken()
          }
        }
        return
      }

      const { data } = await axios.post(`${BASE_URL}/api/v2/auth/twa`, { init_data: initData })
      setAccessToken(data.access_token)
      setTwaRefreshToken(data.refresh_token)
    } catch (err: unknown) {
      // FE-06: только message — axios-err содержит config.data с initData,
      // целиком его в консоль (даже dev) не пишем.
      console.error('TWA auth failed:', err instanceof Error ? err.message : String(err))
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

  // TWA-06 + TWA-08: when the axios interceptor reports refresh failed, clear
  // the token. The effect above then re-runs authenticate() — which on a live
  // Telegram session will succeed via /twa-init with fresh initData rather
  // than dumping the user back to the "Open via Telegram" gate. The
  // shorter TWA refresh TTL (24h server-side) makes this re-init flow the
  // common case for sessions older than a day.
  useEffect(() => {
    const onAuthFailed = () => setAccessToken(null)
    window.addEventListener('twa:auth-failed', onAuthFailed)
    return () => window.removeEventListener('twa:auth-failed', onAuthFailed)
  }, [])

  return { accessToken, isLoading, isAuthenticated: !!accessToken }
}
