import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { testI18n } from '../../test/test-utils'
import { ACCESS_MODULE_ROLES } from '../../constants/roles'
import AccessControlPage from './AccessControlPage'

// ── Мок WebSocket ─────────────────────────────────────────────────────────────
// Заменяем глобальный WebSocket управляемым стабом: тест сам «открывает»
// соединение, шлёт ready/event-фреймы и закрытия, проверяя реакцию хука/страницы.
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static last(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1]
  }

  url: string
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
  }

  // ── управление из теста ──
  emitOpen() {
    this.readyState = 1
    act(() => this.onopen?.())
  }

  emitFrame(obj: unknown) {
    act(() => this.onmessage?.({ data: JSON.stringify(obj) }))
  }

  emitClose(code = 1006) {
    act(() => this.onclose?.({ code }))
  }
}

function renderPage() {
  // Страница монтирует RedeemCodeDialog (useMutation) — нужен QueryClient.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <AccessControlPage />
      </I18nextProvider>
    </QueryClientProvider>,
  )
}

describe('AccessControlPage — live-лента событий охраны', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    // dev-токен не задаём: проверяем cookie-путь (первый кадр не должен слаться).
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('(а) рендерит пришедшее событие с нужными полями и маскированным номером', () => {
    renderPage()
    const ws = MockWebSocket.last()
    ws.emitOpen()
    ws.emitFrame({ type: 'ready' })

    ws.emitFrame({
      type: 'access_event',
      decision: 'allow',
      status: 'allowed',
      reason: 'permanent_vehicle_allowed',
      zone_id: 7,
      gate_id: 3,
      direction: 'entry',
      occurred_at: '2026-06-26T10:00:00+00:00',
      plate_masked: '******AA',
    })

    // Решение (переведено), причина, направление, место, маскированный номер.
    expect(screen.getByText('Разрешён')).toBeInTheDocument()
    expect(screen.getByText('ТС в постоянном списке')).toBeInTheDocument()
    expect(screen.getByText('Въезд')).toBeInTheDocument()
    expect(screen.getByText('Зона 7 · Точка 3')).toBeInTheDocument()
    expect(screen.getByText('******AA')).toBeInTheDocument()
  })

  it('(б) индикатор статуса меняется connecting → open → closed', () => {
    renderPage()
    const ws = MockWebSocket.last()

    // Первичный статус — «Подключение…».
    expect(screen.getByText('Подключение…')).toBeInTheDocument()

    ws.emitOpen()
    ws.emitFrame({ type: 'ready' })
    expect(screen.getByText('На связи')).toBeInTheDocument()

    // Аномальное закрытие → «Соединение разорвано» (и реконнект по backoff).
    ws.emitClose(1006)
    expect(screen.getByText('Соединение разорвано')).toBeInTheDocument()
  })

  it('пустое состояние до первого события', () => {
    renderPage()
    MockWebSocket.last().emitOpen()
    expect(screen.getByText('Пока нет событий доступа')).toBeInTheDocument()
  })

  it('cookie-путь: без dev-токена первый кадр не отправляется', () => {
    renderPage()
    const ws = MockWebSocket.last()
    ws.emitOpen()
    expect(ws.sent).toHaveLength(0)
  })

  it('cookieless-путь: dev-токен из sessionStorage уходит первым кадром', () => {
    sessionStorage.setItem('access_ws_dev_token', 'dev.jwt.token')
    renderPage()
    const ws = MockWebSocket.last()
    ws.emitOpen()
    expect(ws.sent).toHaveLength(1)
    expect(JSON.parse(ws.sent[0])).toEqual({ token: 'dev.jwt.token' })
  })
})

describe('AccessControlPage — гард роли (контракт ACCESS_MODULE_ROLES)', () => {
  // Роут /dashboard/access и пункт сайдбара гейтятся одним и тем же набором
  // ACCESS_MODULE_ROLES. Проверяем контракт: модульные роли допущены,
  // executor/inspector/applicant — нет.
  it('допускает роли модуля и исключает executor/inspector/applicant', () => {
    expect(ACCESS_MODULE_ROLES).toEqual(['manager', 'system_admin', 'security_operator'])
    for (const role of ['executor', 'inspector', 'applicant']) {
      expect(ACCESS_MODULE_ROLES).not.toContain(role)
    }
  })
})
