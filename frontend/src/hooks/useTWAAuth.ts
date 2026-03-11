import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { apiClient } from '../api/client'
import { isTWA, getTWAInitData } from '../utils/isTWA'

export function useTWAAuth() {
  const { isAuthenticated, login } = useAuthStore()
  const [isLoading, setIsLoading] = useState(() => isTWA() && !isAuthenticated)

  useEffect(() => {
    if (isTWA() && !isAuthenticated) {
      setIsLoading(true)
      const init_data = getTWAInitData()
      apiClient.post('/api/v2/auth/twa', { init_data })
        .then(({ data }) => login(data.access_token, data.refresh_token))
        .catch(console.error)
        .finally(() => setIsLoading(false))
    }
  }, [isAuthenticated, login])

  return { isAuthenticated, isLoading }
}
