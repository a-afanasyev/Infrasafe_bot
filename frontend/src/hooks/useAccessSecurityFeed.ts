import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Live-лента событий охраны модуля контроля доступа (ТЗ access_control §9.6, §15.13).
 *
 * Источник — WS-эндпоинт `uk-access-api` `/ws/v1/access/security`. Сообщения
 * PD-safe (§11): без полного номера/фото, только исход и маскированный хвост
 * номера. Точная форма фрейма задаётся `AccessEventMessage.to_payload()`
 * (access_control/services/event_broadcaster.py).
 *
 * ── Авторизация (§9.6) — два пути, конфигурируемые через env ──────────────────
 *
 *  (а) PROD, same-origin за edge: WS проксируется тем же origin, что и SPA, и
 *      браузер сам прикладывает httpOnly cookie web-сессии (`uk_access`) к
 *      upgrade-запросу. JS токен прочитать не может — и не должен. Это путь по
 *      умолчанию: WS-URL вычисляется как same-origin путь под BASE_URL.
 *
 *  (б) DEV / cookieless: в dev дашборд и `uk-access-api` живут на РАЗНЫХ портах
 *      (SPA :3002, access-api :8086) → cookie кросс-origin не уходит. Поэтому
 *      клиент шлёт JWT ПЕРВЫМ WS-сообщением `{"token": "<jwt>"}` (cookieless-путь
 *      сервера). JWT в query string сервером ЗАПРЕЩЁН (§9.6) — только в теле
 *      первого сообщения.
 *
 * Конфигурация (оба пути честно отражают реальное ограничение dev cross-origin):
 *  - `VITE_ACCESS_WS_URL` — полный ws(s)-URL эндпоинта. По умолчанию same-origin
 *    путь `/{BASE_URL}ws/v1/access/security` (прод за edge).
 *  - `VITE_ACCESS_WS_DEV_TOKEN` ИЛИ sessionStorage['access_ws_dev_token'] —
 *    dev-JWT. Если задан, шлётся первым сообщением (путь «б»). Иначе клиент
 *    полагается на cookie (путь «а»). Токен НИКОГДА не логируется.
 */

// PD-safe событие доступа — зеркало AccessEventMessage.to_payload() на бэке.
export interface AccessEvent {
  decision: string
  status: string
  reason: string | null
  zone_id: number | null
  gate_id: number | null
  direction: string | null
  occurred_at: string | null
  plate_masked: string | null
}

export type AccessFeedStatus = 'connecting' | 'open' | 'closed' | 'error'

// Сколько последних событий держим в памяти (live-лента, не история).
const MAX_EVENTS = 100
// WS close code «policy violation» (RFC 6455): отказ авторизации — НЕ реконнектим.
const WS_POLICY_VIOLATION = 1008
const MAX_RECONNECT_ATTEMPTS = 6
const BASE_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 15000

// Ключ sessionStorage для dev-JWT (cookieless-путь). Per-tab, как и web UI-флаг.
export const ACCESS_WS_DEV_TOKEN_KEY = 'access_ws_dev_token'

/** Same-origin путь WS под BASE_URL дашборда (прод за edge: cookie уходит сама). */
function defaultWsUrl(): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '') // напр. "/uk"
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${base}/ws/v1/access/security`
}

/** dev-токен из env или sessionStorage (если задан → cookieless-путь). */
function resolveDevToken(): string | null {
  const fromEnv = import.meta.env.VITE_ACCESS_WS_DEV_TOKEN
  if (fromEnv) return fromEnv
  try {
    return sessionStorage.getItem(ACCESS_WS_DEV_TOKEN_KEY)
  } catch {
    return null
  }
}

export interface AccessSecurityFeed {
  events: AccessEvent[]
  status: AccessFeedStatus
}

export function useAccessSecurityFeed(): AccessSecurityFeed {
  const [events, setEvents] = useState<AccessEvent[]>([])
  const [status, setStatus] = useState<AccessFeedStatus>('connecting')

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const attemptsRef = useRef(0)
  const closedByCaller = useRef(false)
  // Реконнект вызывает connect рекурсивно из onclose. Маршрутизируем через ref,
  // чтобы не ссылаться на binding connect до его объявления (TDZ-смелл).
  const connectRef = useRef<() => void>(() => {})

  const connect = useCallback(() => {
    const url = import.meta.env.VITE_ACCESS_WS_URL || defaultWsUrl()
    setStatus('connecting')

    let ws: WebSocket
    try {
      ws = new WebSocket(url)
    } catch {
      // Сконструировать сокет не удалось (битый URL) — это ошибка конфигурации.
      setStatus('error')
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      attemptsRef.current = 0
      // Cookieless-путь: при наличии dev-токена шлём его ПЕРВЫМ сообщением.
      // Токен не логируется. Без токена — полагаемся на httpOnly cookie (прод).
      const devToken = resolveDevToken()
      if (devToken) {
        ws.send(JSON.stringify({ token: devToken }))
      }
      // Статус 'open' выставим по серверному ready-фрейму (подписка активна).
    }

    ws.onmessage = (e) => {
      let parsed: unknown
      try {
        parsed = JSON.parse(e.data)
      } catch {
        return // не-JSON фрейм игнорируем
      }
      if (!parsed || typeof parsed !== 'object') return
      const frame = parsed as Record<string, unknown>

      if (frame.type === 'ready') {
        // Сервер подтвердил подписку на брокер — соединение боевое.
        setStatus('open')
        return
      }
      if (frame.type === 'access_event') {
        const event: AccessEvent = {
          decision: String(frame.decision ?? ''),
          status: String(frame.status ?? ''),
          reason: frame.reason == null ? null : String(frame.reason),
          zone_id: typeof frame.zone_id === 'number' ? frame.zone_id : null,
          gate_id: typeof frame.gate_id === 'number' ? frame.gate_id : null,
          direction: frame.direction == null ? null : String(frame.direction),
          occurred_at: frame.occurred_at == null ? null : String(frame.occurred_at),
          plate_masked: frame.plate_masked == null ? null : String(frame.plate_masked),
        }
        // Новейшие сверху, обрезаем до MAX_EVENTS (live-лента, не история).
        setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS))
      }
    }

    ws.onerror = () => {
      // Детали не логируем, чтобы случайно не утёк токен из обёрток рантайма.
      setStatus('error')
    }

    ws.onclose = (event) => {
      if (closedByCaller.current) return
      // 1008 (policy violation) = отказ авторизации: реконнект не поможет.
      if (event.code === WS_POLICY_VIOLATION) {
        setStatus('error')
        return
      }
      if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setStatus('closed')
        return
      }
      setStatus('closed')
      const delay = Math.min(BASE_BACKOFF_MS * 2 ** attemptsRef.current, MAX_BACKOFF_MS)
      attemptsRef.current += 1
      reconnectTimer.current = setTimeout(() => connectRef.current(), delay)
    }
  }, [])

  useEffect(() => {
    closedByCaller.current = false
    connectRef.current = connect
    connect()
    return () => {
      closedByCaller.current = true
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { events, status }
}
