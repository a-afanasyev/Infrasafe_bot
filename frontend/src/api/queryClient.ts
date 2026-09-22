import { QueryClient } from '@tanstack/react-query'

// Единственный QueryClient веб-дашборда. Вынесен из App.tsx, чтобы authStore
// мог чистить кэш на logout/login (A9-P2-29): иначе следующий пользователь в той
// же вкладке видел канбан, ПДн жителей и media-blob предыдущего. TWA держит
// свой клиент (twa/App.tsx) — там нет выхода, сессия = Telegram initData.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

/**
 * Сбросить весь серверный кэш текущей сессии. `clear()` отменяет in-flight
 * запросы (query.destroy → cancel), так что поздний ответ старой сессии в кэш
 * уже не попадёт. Смонтированные observer'ы сами не рефетчат — выход сразу
 * размонтирует защищённые роуты. media-blob — data: URL, revoke не требуется.
 */
export function resetSessionCache(): void {
  queryClient.clear()
}
