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

// F-04 (остаток): 4003 — доступ отозван УЖЕ во время сессии: пользователя
// заблокировали или сняли роль manager. В отличие от 4001 обновлять сессию
// бессмысленно — новый токен выдадут тому же заблокированному пользователю, и
// сервер закроет соединение снова. Ведём себя как на 1008: молча стоп.
const WS_ACCESS_REVOKED = 4003

// П4: отказ ДО upgrade close-кода не имеет. Сервер закрывает соединение до
// accept(), uvicorn отвечает HTTP 403 — и браузерный WebSocket API HTTP-статус
// проваленного хендшейка не отдаёт: событие приходит как 1006, а `onopen` не
// вызывается вовсе. Поэтому «cookie просрочена» и «сервер недоступен» здесь
// неразличимы, и единственный доступный признак pre-upgrade отказа — «закрылось,
// ни разу не открывшись». Отсюда стратегия: одна попытка обновить сессию в то же
// 30-секундное окно, что и для 4001, дальше обычный backoff. Контракт провода
// прибит тестом tests/api/test_ws_wire_protocol.py.
//
// Числовые readyState вместо WebSocket.OPEN: константы читаются с глобального
// конструктора, который в тестах подменяется целиком.
const WS_STATE_CONNECTING = 0
const WS_STATE_OPEN = 1

export function useWebSocket(
  endpoint: 'kanban' | 'shifts' | 'buildings' | 'apartments',
  onMessage: (event: { type: string; data: unknown }) => void
) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const attemptsRef = useRef(0)
  const lastExpiredRefreshAt = useRef(0)
  const openedRef = useRef(false)
  // AUD6-P2-13: cleanup закрывает сокет и снимает таймер, но промис
  // refreshSession().then(connect) он отменить не может — без этого флага
  // resolve ПОСЛЕ размонтирования создавал бы новый сокет, который уже никто
  // не закроет (эталон — closedByCaller в useAccessSecurityFeed).
  const closedByCaller = useRef(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    // Browser sends httpOnly cookie automatically with the WebSocket upgrade request
    const ws = new WebSocket(`${WS_URL}/ws/v2/${endpoint}`)
    wsRef.current = ws
    openedRef.current = false

    ws.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data)
        onMessageRef.current(parsed)
      } catch { /* ignore parse errors */ }
    }

    ws.onopen = () => {
      openedRef.current = true
      attemptsRef.current = 0
    }

    /** Обновить сессию и вернуться — не чаще раза в окно, иначе это цикл. */
    const refreshAndReconnect = (): boolean => {
      const now = Date.now()
      if (now - lastExpiredRefreshAt.current < EXPIRED_REFRESH_MIN_INTERVAL_MS) {
        return false
      }
      lastExpiredRefreshAt.current = now
      // Провал refresh уже редиректит на /login внутри refreshSession.
      refreshSession().then(() => {
        // eslint-disable-next-line react-hooks/immutability -- намеренная рекурсивная ссылка на connect для reconnect (стабильна: connect мемоизирован по endpoint)
        if (!closedByCaller.current) connect()
      }).catch(() => {})
      return true
    }

    ws.onclose = (event) => {
      if (event.code === WS_TOKEN_EXPIRED) {
        refreshAndReconnect() // отказ в окне — молча стоп, свежий токен живёт ~60 мин
        return
      }
      if (event.code === 1008 || event.code === WS_ACCESS_REVOKED) {
        // Policy violation / доступ отозван — ретраи бессмысленны, стоп.
        // 1008 достижим только для cookieless-клиентов (first-message auth):
        // у SPA отказ аутентификации приходит ветвью ниже.
        return
      }
      if (!openedRef.current && refreshAndReconnect()) {
        return // возможно, дело в просроченной cookie — одна попытка за окно
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
    closedByCaller.current = false
    connect()
    return () => {
      closedByCaller.current = true
      wsRef.current?.close()
      clearTimeout(reconnectTimer.current)
    }
  }, [connect])

  // AUD5-APIFE-7: исчерпав MAX_RECONNECT_ATTEMPTS, хук замолкал до перезагрузки
  // страницы — уснувший ноутбук или пропавший wifi оставляли доску мёртвой, хотя
  // браузер прямо сообщает и о возврате связи, и о возврате пользователя.
  useEffect(() => {
    const revive = () => {
      if (document.visibilityState === 'hidden') return
      const ws = wsRef.current
      if (ws && (ws.readyState === WS_STATE_OPEN || ws.readyState === WS_STATE_CONNECTING)) {
        return // соединение живо или уже поднимается — второй сокет не нужен
      }
      attemptsRef.current = 0
      clearTimeout(reconnectTimer.current)
      connect()
    }

    window.addEventListener('online', revive)
    document.addEventListener('visibilitychange', revive)
    return () => {
      window.removeEventListener('online', revive)
      document.removeEventListener('visibilitychange', revive)
    }
  }, [connect])
}
