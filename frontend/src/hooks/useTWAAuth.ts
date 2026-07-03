import { useCallback, useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { publicClient } from '../api/client'
import { isTWA, getTWAInitData } from '../utils/isTWA'

export function useTWAAuth() {
  const { isAuthenticated, login } = useAuthStore()
  const [isLoading, setIsLoading] = useState(() => isTWA() && !isAuthenticated)
  // FE-05: сбой аутентификации раньше проглатывался (.catch(console.error)) —
  // страница оставалась пустой без объяснения. Теперь возвращаем isError +
  // retry, чтобы UI показал ошибку и кнопку повтора.
  const [isError, setIsError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => {
    setIsError(false)
    setAttempt(a => a + 1)
  }, [])

  useEffect(() => {
    if (isTWA() && !isAuthenticated) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- намеренная установка loading-состояния перед async-авторизацией на mount
      setIsLoading(true)
      setIsError(false)
      const init_data = getTWAInitData()
      // FE-047-семейство: publicClient — авторизация не должна триггерить
      // 401-interceptor (refresh→redirect на /login внутри Telegram WebView).
      publicClient.post('/api/v2/auth/twa', { init_data })
        .then(() => login())
        .catch((err: unknown) => {
          setIsError(true)
          // FE-06-гигиена: только message, без объекта с initData внутри.
          console.error('TWA auth failed:', err instanceof Error ? err.message : String(err))
        })
        .finally(() => setIsLoading(false))
    }
  }, [isAuthenticated, login, attempt])

  return { isAuthenticated, isLoading, isError, retry }
}
