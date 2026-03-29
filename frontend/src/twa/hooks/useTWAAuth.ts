import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { useTelegramSDK } from './useTelegramSDK'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

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

  useEffect(() => { authenticate() }, [authenticate])

  return { accessToken, isLoading, isAuthenticated: !!accessToken }
}
