import { QueryClient } from '@tanstack/react-query'
import { apiErrorStatus } from '../utils/errorMessage'

// Мобильная сеть у исполнителя рвётся: без повторов одиночный сбой сразу
// превращался в экран ошибки. Задержка — дефолтный экспоненциальный backoff.
const MAX_QUERY_RETRIES = 2

/** Повторять чтение при сбое сети/5xx/408/429; прочие 4xx — ответ окончательный. */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_QUERY_RETRIES) return false
  const status = apiErrorStatus(error)
  if (status !== null && status >= 400 && status < 500) return status === 408 || status === 429
  return true
}

// Мутации не повторяем автоматически: повтор неидемпотентной операции
// (смена статуса, отчёт) — решение пользователя, не клиента.
export function createTwaQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetryQuery, staleTime: 30_000 },
      mutations: { retry: false },
    },
  })
}
