import { useEffect, useRef, useCallback } from 'react'

import { refreshSession } from '../api/client'

// WS path is namespaced under the SPA base (e.g. wss://infrasafe.uz/uk/ws/v2/...).
// VITE_WS_URL still wins for tests / dev with a non-default backend.
const BASE_PATH = import.meta.env.BASE_URL.replace(/\/$/, '') // "/uk"
const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${BASE_PATH}`
const MAX_RECONNECT_ATTEMPTS = 5

// F-04: сервер закрывает стрим по истечению JWT кодом 4001 — обновляем сессию
// (httpOnly cookie) и переподключаемся. Свежий токен живёт ~60 мин, поэтому
// второй 4001 раньше этого окна означает, что refresh не помогает — стоп,
// иначе цикл refresh/reconnect каждые пару секунд.
const WS_TOKEN_EXPIRED = 4001
const EXPIRED_REFRESH_MIN_INTERVAL_MS = 30_000

export function useWebSocket(
  endpoint: 'kanban' | 'shifts' | 'buildings',
  onMessage: (event: { type: string; data: unknown }) => void
) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const attemptsRef = useRef(0)
  const lastExpiredRefreshAt = useRef(0)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    // Browser sends httpOnly cookie automatically with the WebSocket upgrade request
    const ws = new WebSocket(`${WS_URL}/ws/v2/${endpoint}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data)
        onMessageRef.current(parsed)
      } catch { /* ignore parse errors */ }
    }

    ws.onopen = () => {
      attemptsRef.current = 0
    }

    ws.onclose = (event) => {
      if (event.code === WS_TOKEN_EXPIRED) {
        const now = Date.now()
        if (now - lastExpiredRefreshAt.current < EXPIRED_REFRESH_MIN_INTERVAL_MS) {
          return // refresh не даёт живущий токен — не зацикливаемся
        }
        lastExpiredRefreshAt.current = now
        // Провал refresh уже редиректит на /login внутри refreshSession.
        // eslint-disable-next-line react-hooks/immutability -- намеренная рекурсивная ссылка на connect для reconnect (стабильна: connect мемоизирован по endpoint)
        refreshSession().then(connect).catch(() => {})
        return
      }
      if (event.code === 1008) {
        // Policy violation — auth denied, don't retry
        return
      }
      if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        console.warn(`WebSocket [${endpoint}] disconnected after ${MAX_RECONNECT_ATTEMPTS} attempts`)
        return
      }
      attemptsRef.current += 1
      // eslint-disable-next-line react-hooks/immutability -- намеренная рекурсивная ссылка на connect для reconnect (стабильна: connect мемоизирован по endpoint)
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [endpoint])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      clearTimeout(reconnectTimer.current)
    }
  }, [connect])
}
