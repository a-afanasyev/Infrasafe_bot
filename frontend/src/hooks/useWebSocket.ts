import { useEffect, useRef, useCallback } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
const MAX_RECONNECT_ATTEMPTS = 5

export function useWebSocket(
  endpoint: 'kanban' | 'shifts',
  onMessage: (event: { type: string; data: unknown }) => void
) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const attemptsRef = useRef(0)
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
      if (event.code === 1008) {
        // Policy violation — expired token, don't retry
        return
      }
      if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        console.warn(`WebSocket [${endpoint}] disconnected after ${MAX_RECONNECT_ATTEMPTS} attempts`)
        return
      }
      attemptsRef.current += 1
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
